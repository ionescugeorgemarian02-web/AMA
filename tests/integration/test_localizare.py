"""F16.3 — a doua limbă. „Gata când”: un client care alege engleza vede portalul în engleză (HTTP, cu CSRF), iar un
client setat pe engleză primește instrucțiunea de limbă în contextul autorilor și e validat pe regulile englezei
(textul în română pică G1, cel în engleză trece G1 și G10). Fără model real (D-007)."""

import datetime as dt
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app import localizare
from app.conturi import Rol
from app.db import sesiune_agentie, sesiune_tenant
from app.validare import limba, structura
from app.validare.intrare import Continut, Intrare, SituatieLivrabil
from app.validare.verdict import Rezultat
from tests.integration.conftest import Cont, csrf_din, login

pytestmark = pytest.mark.db
EN = ("Our new chocolate cake is ready for the weekend, and you can order it today from the shop "
      "or online, with delivery in the city.")  # fmt: skip
RO = ("Tortul nostru nou de ciocolată este gata pentru weekend și îl poți comanda azi din cofetărie "
      "sau online, cu livrare în oraș.")  # fmt: skip


def test_portalul_in_engleza_dupa_alegerea_limbii(
    client: TestClient, fabrica_conturi: Callable[..., Cont]
) -> None:
    cont = fabrica_conturi(Rol.CLIENT_TITULAR)
    assert login(client, cont.email, cont.parola).status_code == 303
    h = client.get("/portal")
    assert h.status_code == 200 and "Aprobări" in h.text and '<html lang="ro">' in h.text
    assert client.post("/portal/limba", data={"limba": "en"}, follow_redirects=False).status_code == 403
    r = client.post(
        "/portal/limba", data={"limba": "en", "csrf_token": csrf_din(h.text)}, follow_redirects=False
    )
    assert r.status_code == 303 and "ama_limba=en" in r.headers["set-cookie"]
    e = client.get("/portal")
    assert (
        '<html lang="en">' in e.text and "Approvals" in e.text and "Getting started, step by step" in e.text
    )
    assert "Aprobări" not in e.text


def test_clientul_pe_engleza_e_scris_si_validat_in_engleza(fabrica_conturi: Callable[..., Cont]) -> None:
    t = fabrica_conturi(Rol.CLIENT_TITULAR).tenant_id
    assert t is not None
    with sesiune_agentie() as db:
        localizare.seteaza_limba_client(db, t, "en")
    with sesiune_tenant(t) as db:
        assert localizare.limba_client(db, t) == "en"

        class Lv:
            tenant_id = t

        assert "English" in localizare.adaos_context(db, Lv())
        sit = SituatieLivrabil(t, t, "postare", "facebook", 1, 0)
        la = dt.datetime(2026, 11, 18, tzinfo=dt.UTC)
        ro, en = Intrare(sit, Continut(1, RO), la, db=db), Intrare(sit, Continut(1, EN), la, db=db)
        assert structura.g1(ro).rezultat is Rezultat.ESEC
        assert structura.g1(en).rezultat is not Rezultat.ESEC
        assert limba.g10_reguli(en).rezultat is not Rezultat.ESEC
    with pytest.raises(ValueError), sesiune_agentie() as db:
        localizare.seteaza_limba_client(db, t, "fr")
