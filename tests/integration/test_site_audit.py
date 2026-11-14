"""F7.2 — formularul de audit. „Gata când”: un audit cerut produce un raport și un lead în sistem. Opt-in dublu:
fără confirmarea din email nu rulează nimic. Emailul trece prin efectele de sistem (outbox, job durabil) spre cutia
poștală SIMULATĂ; motorul de audit (BigBrain, prin rețea) e adaptorul SIMULAT."""

# ruff: noqa: F811
import time
from collections.abc import Callable
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.connectors.email import CutiePostalaSimulata
from app.conturi import Rol
from app.db import sesiune_agentie
from app.site import audit
from app.site.modele import Audit, Lead
from tests.integration.conftest import Cont, csrf_din
from tests.integration.utile_panou import autentifica
from tests.integration.utile_site import asteapta, cutie, link_din  # noqa: F401

pytestmark = pytest.mark.db
EMAIL = "contact@zorilor.example"


def lead(email: str) -> Lead | None:
    with sesiune_agentie() as db:
        return db.execute(select(Lead).where(Lead.email == email)).scalar_one_or_none()


def date(client: TestClient, **extra: str) -> dict[str, str]:
    h = client.get("/site/audit").text
    return {"csrf_token": csrf_din(h), "firma": "Cafeneaua Zorilor", "site_url": "zorilor.example",
            "email": EMAIL, "acord": "da", "t": audit.jeton_formular(time.time() - 10), **extra}  # fmt: skip


def test_audit_cerut_confirmat_produce_raport_si_lead(
    client: TestClient, cutie: CutiePostalaSimulata, executor: None, fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
) -> None:  # fmt: skip
    h = client.get("/site/audit").text
    assert 'name="site_web2"' in h and 'name="acord"' in h and "opt-in dublu" in h
    assert client.post("/site/audit", data={**date(client), "csrf_token": "x"}).status_code == 403
    # spam: completat prea repede / câmpul-capcană → același răspuns, nimic salvat
    t_proaspat = h.split('name="t" value="')[1].split('"')[0]
    for extra in ({"t": t_proaspat}, {"site_web2": "http://spam.example"}):
        r = client.post("/site/audit", data=date(client, **extra))
        assert r.status_code == 200 and "Verifică-ți emailul" in r.text
    assert lead(EMAIL) is None
    r = client.post("/site/audit", data=date(client, email="nu-e-email"))
    assert r.status_code == 422 and "nu este validă" in r.text
    r = client.post("/site/audit", data=date(client, acord=""))
    assert r.status_code == 422 and "acordul" in r.text
    r = client.post("/site/audit", data=date(client))
    assert r.status_code == 200 and "Verifică-ți emailul" in r.text
    l0 = lead(EMAIL)
    assert l0 is not None and l0.stare == "neconfirmat" and l0.site_url == "https://zorilor.example"
    [confirmare] = asteapta(lambda: cutie.catre(EMAIL))
    assert "Confirmă" in confirmare.subiect
    with sesiune_agentie() as db:  # fără confirmare nu rulează nimic
        assert db.execute(select(Audit).where(Audit.lead_id == l0.id)).first() is None
    link = link_din(confirmare.text, "/audit/confirma/")
    r = client.get(urlsplit(link).path)
    assert r.status_code == 200 and "confirmată" in r.text
    raport_mail = asteapta(lambda: next((m for m in cutie.catre(EMAIL) if "Raportul" in m.subiect), None))
    l1 = lead(EMAIL)
    assert l1 is not None and l1.stare == "audit_gata" and l1.confirmat_la is not None
    r = client.get(urlsplit(link_din(raport_mail.text, "/audit/raport/")).path)
    assert r.status_code == 200 and "Trei lucruri de făcut" in r.text and r.text.count("<li>") >= 6
    assert '<meta name="robots" content="noindex">' in r.text
    assert client.get(urlsplit(link).path).status_code == 404  # jetonul de confirmare nu mai e valabil
    # a doua cerere pe aceeași adresă nu trimite nimic nou
    client.post("/site/audit", data=date(client))
    time.sleep(0.5)
    assert len(cutie.catre(EMAIL)) == 2
    # lead-ul apare în panou
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    h = client.get("/leaduri").text
    assert "Cafeneaua Zorilor" in h and "raport trimis" in h


def test_jetonul_formularului_semnat_si_cu_timp_minim() -> None:
    acum = time.time()
    t = audit.jeton_formular(acum - 60)
    assert audit.verifica_jeton_formular(t, acum)
    assert not audit.verifica_jeton_formular(audit.jeton_formular(acum - 1), acum)
    assert not audit.verifica_jeton_formular(t.replace(".", ".0"), acum)
    assert not audit.verifica_jeton_formular(audit.jeton_formular(acum - 2 * 86400), acum)
