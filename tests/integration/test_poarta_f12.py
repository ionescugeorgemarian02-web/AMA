"""Poarta F12 — CRM, email, inbox (docs/23 §23.15): un lead parcurge drumul de la audit la apel programat.

Cap-coadă, pe simulare (# SIMULAT: cutia poștală, motorul de audit; timpul secvenței e mutat înainte):
1. Formularul de audit → confirmarea adresei (opt-in dublu) → lead în CRM cu sursă și temei → raportul de audit.
2. Secvența de după audit: pașii 1–3 pleacă prin ușa unică de email (cu dezabonare); pasul 3 duce la programare.
3. Din linkul din email, de pe telefon: întrebările de calificare și rezervarea apelului → același lead (fără
   dublură), calificat „de sunat azi”, în „apel programat”, cu invitația .ics primită și sarcina pentru om.
4. Secvența de hrănire se oprește singură; proprietarul vede lead-ul în CRM; urmele leagă fiecare pas.
"""

# ruff: noqa: F811
import datetime as dt
import re
import time
import uuid
from collections.abc import Callable, Iterator
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text

from app.connectors.email import CutiePostalaSimulata
from app.conturi import Rol
from app.crm import Sarcina, calificare, email, registru, secventa
from app.db import sesiune_agentie
from app.site import audit as site_audit
from tests.integration.conftest import Cont, csrf_din
from tests.integration.test_site_audit import date as date_formular
from tests.integration.utile_crm import curata_crm
from tests.integration.utile_panou import autentifica
from tests.integration.utile_site import asteapta, cutie, link_din  # noqa: F401

pytestmark = pytest.mark.db
TELEFON = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1"}


@pytest.fixture(autouse=True)
def _curat(admin_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    curata_crm(admin_engine)
    monkeypatch.setattr(email, "REZOLVA", lambda d: True)  # DNS-ul domeniului de test
    yield
    curata_crm(admin_engine)


def test_un_lead_parcurge_drumul_de_la_audit_la_apel_programat(
    client: TestClient, cutie: CutiePostalaSimulata, executor: None, fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float], admin_engine: Engine,
) -> None:  # fmt: skip
    adresa = f"poarta-{uuid.uuid4().hex[:8]}@zorilor.example"
    # 1. auditul, cu opt-in dublu
    assert client.post("/site/audit", data=date_formular(client, email=adresa)).status_code == 200
    [confirmare] = asteapta(lambda: cutie.catre(adresa))
    assert client.get(urlsplit(link_din(confirmare.text, "/audit/confirma/")).path).status_code == 200
    with sesiune_agentie() as db:
        [(lead, contact, _)] = registru.lista(db)
        lead_id, cid, site_id = lead.id, contact.id, lead.lead_site_id
        assert (lead.sursa, lead.temei, lead.etapa) == ("formular_audit", "solicitare_si_opt_in", "nou")
        s = secventa.stare(db, cid)
        assert s is not None
        pornita = s.pornita_la
    assert site_id is not None

    def raport() -> bool | None:
        with sesiune_agentie() as db:
            return site_audit.raport_pentru_lead(db, site_id) is not None or None

    asteapta(raport)

    # 2. secvența: trei pași, fiecare prin ușa unică, cu dezabonare
    for zi in (2, 5, 9):
        assert secventa.ruleaza(pornita + dt.timedelta(days=zi, minutes=1))["trimise"] == 1
    pasi = asteapta(lambda: (lambda x: x if len(x) == 3 else None)(
        [m for m in cutie.catre(adresa) if "List-Unsubscribe" in m.antete]
    ))  # fmt: skip
    [invitatie_la_apel] = [m for m in pasi if m.subiect == "Vreți să trecem împreună prin audit?"]
    [link] = re.findall(r"https?://\S+/programare\b", invitatie_la_apel.text)
    cale = urlsplit(link).path
    assert cale == "/site/programare"

    # 3. de pe telefon: calificarea și rezervarea apelului
    h = client.get(cale, headers=TELEFON)
    assert h.status_code == 200 and "asistentul AI" in h.text
    ales = re.findall(r'name="slot" value="([^"]+)"', h.text)[0]
    date = {"csrf_token": csrf_din(h.text), "t": site_audit.jeton_formular(time.time() - 10), "slot": ales,
            "nume": "Ana", "firma": "Cafeneaua Zorilor", "email": adresa, "nisa": "horeca",
            "buget": "3000_10000", "termen": "imediat", "decident": "da"}  # fmt: skip
    r = client.post(cale, data=date, headers=TELEFON)
    assert r.status_code == 200 and "Apel programat" in r.text
    [inv] = asteapta(lambda: [m for m in cutie.catre(adresa) if m.subiect.startswith("Confirmat:")] or None)
    assert "METHOD:REQUEST" in inv.atasamente[0]["continut"]
    with sesiune_agentie() as db:
        [(l2, c2, _)] = registru.lista(db)
        assert (l2.id, c2.id) == (lead_id, cid), "același lead, fără dublură"
        assert l2.etapa == "apel_programat"
        c = calificare.curenta(db, lead_id)
        assert c is not None and c.grupa == "suna_azi"
        assert any(
            x.titlu.startswith("Apel cu")
            for x in db.scalars(select(Sarcina).where(Sarcina.lead_id == lead_id))
        )
        assert registru.are_consimtamant(db, cid, "email_audit"), "programarea nu atinge acordul dat"

    # 4. secvența se oprește singură; proprietarul vede lead-ul; urmele leagă pașii
    assert secventa.ruleaza(pornita + dt.timedelta(days=14, minutes=1)) == {
        "trimise": 0,
        "oprite": 1,
        "amanate": 0,
    }
    with sesiune_agentie() as db:
        s = secventa.stare(db, cid)
        assert s is not None and (s.stare, s.motiv_oprire) == ("oprita", "lead_apel_programat")
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    h = client.get("/crm?etapa=apel_programat").text
    assert "Cafeneaua Zorilor" in h
    h = client.get(f"/crm/lead/{lead_id}").text
    assert "de sunat azi" in h and "Apel programat:" in h
    with admin_engine.begin() as conn:
        actiuni = {
            r[0] for r in conn.execute(text("SELECT DISTINCT actiune FROM urme WHERE componenta = 'crm'"))
        }
    assert {"secventa_inscriere", "secventa_pas", "calificare", "programare", "secventa_oprita"} <= actiuni
