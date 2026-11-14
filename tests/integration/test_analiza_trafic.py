"""F10.6 — analiza de trafic proprie. „Gata când”: vezi câți vizitatori cer audit. Vizitele se numără doar
cu acord (cookie-ul de consimțământ), cererile de audit sunt exacte."""

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.analiza import trafic
from app.conturi import Rol
from app.db import sesiune_agentie
from app.site import analiza as analiza_site
from app.site.modele import Lead
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica

pytestmark = pytest.mark.db
AZI = dt.datetime.now(dt.UTC).date()


@pytest.fixture(autouse=True)
def _curat(admin_engine: Engine) -> None:
    with admin_engine.begin() as c:  # tabelele site-ului sunt ale agenției, comune pe sesiunea de teste
        c.execute(text("DELETE FROM site_vizite"))
        c.execute(text("DELETE FROM audituri"))
        c.execute(text("DELETE FROM leaduri"))


def lead(stare: str, sursa: str = "audit", *, zile_in_urma: int = 0) -> None:
    acum = dt.datetime.now(dt.UTC) - dt.timedelta(days=zile_in_urma)
    with sesiune_agentie() as db:
        db.add(
            Lead(
                email=f"{uuid.uuid4().hex[:8]}@exemplu.test",
                firma="Firma de Probă",
                site_url="https://exemplu.test",
                sursa=sursa,
                stare=stare,
                jeton_hash=uuid.uuid4().hex,
                consimtamant_la=acum,
                confirmat_la=None if stare == "neconfirmat" else acum,
                creat_la=acum,
            )
        )


def test_vezi_cati_vizitatori_cer_audit(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float]
) -> None:
    # vizitatori reali ai site-ului: doar cel cu acord e numărat
    assert client.get("/site/audit").status_code == 200
    client.cookies.set(analiza_site.COOKIE, "analiza")
    for _ in range(3):
        assert client.get("/site/audit").status_code == 200
    analiza_site.inregistreaza("/")
    client.cookies.delete(analiza_site.COOKIE)
    assert analiza_site.vizite().get(trafic.PAGINA_AUDIT) == 3, "fără acord nu se numără nimic"
    for _ in range(17):  # restul traficului zilei, cu acord
        analiza_site.inregistreaza(trafic.PAGINA_AUDIT)
    analiza_site.inregistreaza("/preturi", zi=AZI - dt.timedelta(days=40))  # în afara intervalului
    for stare in ("neconfirmat", "confirmat", "audit_gata", "client"):
        lead(stare)
    lead("confirmat", "captare")
    lead("client", zile_in_urma=45)  # în afara intervalului

    with sesiune_agentie() as db:
        p = trafic.palnie(db, AZI - dt.timedelta(days=29), AZI)
    assert (p.vizite, p.vizite_audit) == (21, 20)
    assert (p.cereri, p.confirmate, p.audituri_gata, p.clienti) == (5, 4, 2, 1)
    assert p.cereri_la_suta == 25.0 and p.pe_sursa == {"audit": 4, "captare": 1}
    assert p.pe_pagina[0] == ("/audit", 20)

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    h = client.get("/analiza/trafic").text
    assert '<th scope="row">Cereri de audit</th><td><strong>5</strong></td>' in h
    assert '<th scope="row">Vizite numărate pe pagina de audit</th><td>20</td>' in h
    assert "Cel mult <strong>25.0</strong> cereri la 100 de vizite" in h
    assert "doar pentru vizitatorii care au acceptat analiza" in h
    assert "captare: 1" in h and "/audit: 20" in h and "/preturi" not in h
    assert "/analiza/trafic" in client.get("/analiza").text
    assert client.get("/analiza/trafic?zile=99999").status_code == 200


def test_fara_vizite_numarate_nu_exista_rata(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float]
) -> None:
    lead("neconfirmat")
    with sesiune_agentie() as db:
        p = trafic.palnie(db, AZI, AZI)
    assert (p.vizite_audit, p.cereri, p.cereri_la_suta) == (0, 1, None)
    autentifica(client, fabrica_conturi(Rol.ANALIST, cu_totp=True), ceas)
    h = client.get("/analiza/trafic?zile=7").text
    assert "nu se poate calcula o rată" in h and "Nicio vizită numărată" in h
