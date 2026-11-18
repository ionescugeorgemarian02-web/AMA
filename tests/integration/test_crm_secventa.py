"""F12.3 — secvența de după audit. „Gata când”: un abonat de test primește secvența și dezabonarea funcționează.
Furnizorul de email e cutia poștală SIMULATĂ; verificarea domeniului (DNS) e înlocuită în teste."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable, Iterator
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.connectors.email import CutiePostalaSimulata, Mesaj
from app.crm import email, registru, secventa
from app.db import sesiune_agentie
from tests.integration.conftest import Cont
from tests.integration.test_site_audit import date as date_formular
from tests.integration.utile_crm import curata_crm
from tests.integration.utile_site import asteapta, cutie, link_din  # noqa: F401

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _curat(admin_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    curata_crm(admin_engine)
    monkeypatch.setattr(email, "REZOLVA", lambda d: True)
    yield
    curata_crm(admin_engine)


def din_secventa(c: CutiePostalaSimulata, adresa: str) -> list[Mesaj]:
    inceputuri = tuple(p.subiect.split("{")[0] for p in secventa.PASI)
    return [m for m in c.catre(adresa) if m.subiect.startswith(inceputuri)]


def inscriere(cid: uuid.UUID) -> tuple[str, int, str]:
    with sesiune_agentie() as db:
        s = secventa.stare(db, cid)
        assert s is not None
        return s.stare, s.pas, s.motiv_oprire


def test_abonatul_de_test_primeste_secventa_si_dezabonarea_o_opreste(
    client: TestClient, cutie: CutiePostalaSimulata, executor: None, fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float], admin_engine: Engine,
) -> None:  # fmt: skip
    adresa = f"secv-{uuid.uuid4().hex[:8]}@zorilor.example"
    assert client.post("/site/audit", data=date_formular(client, email=adresa)).status_code == 200
    [confirmare] = asteapta(lambda: cutie.catre(adresa))
    assert client.get(urlsplit(link_din(confirmare.text, "/audit/confirma/")).path).status_code == 200
    assert client.get(urlsplit(link_din(confirmare.text, "/audit/confirma/")).path).status_code == 200
    with sesiune_agentie() as db:
        [(lead, contact, _)] = registru.lista(db)
        cid = contact.id
        s = secventa.stare(db, cid)
        assert s is not None and s.lead_id == lead.id, "confirmarea înscrie contactul, o singură dată"
        pornita = s.pornita_la
    assert inscriere(cid) == ("activa", 0, "")

    assert secventa.ruleaza(pornita + dt.timedelta(hours=1))["trimise"] == 0, "nimic înainte de ziua 2"
    assert secventa.ruleaza(pornita + dt.timedelta(days=2, minutes=1))["trimise"] == 1
    assert secventa.ruleaza(pornita + dt.timedelta(days=2, minutes=2))["trimise"] == 0, (
        "un pas o singură dată"
    )
    asteapta(lambda: din_secventa(cutie, adresa) or None)
    assert secventa.ruleaza(pornita + dt.timedelta(days=5, minutes=1))["trimise"] == 1
    [m1, m2] = asteapta(lambda: (lambda x: x if len(x) == 2 else None)(din_secventa(cutie, adresa)))
    assert m1.subiect.startswith("Primele trei lucruri") and "Cafeneaua Zorilor" in m1.subiect
    assert "List-Unsubscribe" in m2.antete and "Dezabonează-te" in m2.text
    assert inscriere(cid) == ("activa", 2, "")

    # dezabonarea dintr-un clic oprește restul secvenței, definitiv
    cale = urlsplit(link_din(m2.text, "/dezabonare/")).path
    assert client.post(cale).status_code == 200
    r = secventa.ruleaza(pornita + dt.timedelta(days=9, minutes=1))
    assert r == {"trimise": 0, "oprite": 1, "amanate": 0}
    assert inscriere(cid) == ("oprita", 2, "suprimat")
    assert secventa.ruleaza(pornita + dt.timedelta(days=30))["trimise"] == 0
    assert len(din_secventa(cutie, adresa)) == 2, "după dezabonare nu a mai plecat nimic din secvență"
    with admin_engine.begin() as c:
        actiuni = {
            r[0] for r in c.execute(text("SELECT actiune FROM urme WHERE componenta = 'crm' AND obiect_id = :o"), {"o": str(cid)})
        }  # fmt: skip
    assert {"secventa_inscriere", "secventa_pas", "secventa_oprita"} <= actiuni


def contact_inscris(adresa: str, acum: dt.datetime) -> tuple[uuid.UUID, uuid.UUID]:
    with sesiune_agentie() as db:
        lead, _ = registru.primeste(db, email=adresa, firma=f"Firma {adresa[:3]}", sursa="formular_audit")
        assert secventa.inscrie(db, lead.contact_id, lead_id=lead.id, acum=acum)
        assert not secventa.inscrie(db, lead.contact_id, lead_id=lead.id, acum=acum), "a doua oară: nimic"
        return lead.contact_id, lead.id


def test_lead_avansat_acord_retras_si_amanarea_temporara(
    cutie: CutiePostalaSimulata, executor: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    acum = dt.datetime.now(dt.UTC)
    avansat, lead = contact_inscris("ion@avansat.example", acum)
    retras, _ = contact_inscris("eva@retras.example", acum)
    amanat, _ = contact_inscris("dan@amanat.example", acum)
    with sesiune_agentie() as db:
        registru.muta_etapa(db, lead, "apel_programat", utilizator_id=None)
        registru.noteaza_consimtamant(
            db, retras, "email_audit", acordat=False, sursa="formular_audit", temei="solicitare_si_opt_in"
        )
    real = email.stare

    def oprit_pentru_dan(db: object, a: dt.datetime | None = None) -> dict[str, object]:
        return {**real(db, a), "oprit": True}  # type: ignore[arg-type]

    with sesiune_agentie() as db:  # dan: pragurile sunt temporar depășite
        monkeypatch.setattr(email, "stare", oprit_pentru_dan)
        r = secventa.avanseaza(db, acum + dt.timedelta(days=3))
    assert r == {"trimise": 0, "oprite": 2, "amanate": 1}
    assert inscriere(avansat) == ("oprita", 0, "lead_apel_programat"), "cine a cerut un apel nu mai e hrănit"
    assert inscriere(retras) == ("oprita", 0, "fara_consimtamant")
    assert inscriere(amanat) == ("activa", 0, ""), "pragurile sunt temporare: pasul se reîncearcă"
    monkeypatch.setattr(email, "stare", real)
    assert secventa.ruleaza(acum + dt.timedelta(days=3, hours=1))["trimise"] == 1
    assert inscriere(amanat) == ("activa", 1, "")
