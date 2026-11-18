"""FT.5 — ecranul „Urme”: raportul lunii, generarea, firul, exporturile CSV/JSON; doar proprietarul."""

# ruff: noqa: F811
import csv
import datetime as dt
import io
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.conturi import Rol
from app.ids import new_id
from app.operare import urme
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401

pytestmark = pytest.mark.db
LA = dt.datetime(2033, 2, 14, 10, tzinfo=dt.UTC)


def date_luna(tenant: uuid.UUID) -> tuple[str, uuid.UUID]:
    with urme.corelare(tenant_id=tenant) as fir:
        sursa = new_id()
        urme.emite("http", "POST /publicare", id=sursa, la=LA)
        urme.emite(
            "efecte", "publica:facebook", cauza_id=sursa, rezultat="esec", cod="500", motiv="platforma", la=LA
        )
    return fir, sursa


def test_proprietarul_vede_genereaza_si_exporta(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float], tenant: uuid.UUID
) -> None:
    fir, _ = date_luna(tenant)
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    assert 'href="/urme"' in client.get("/meniu").text
    h = client.get("/urme?luna=2033-02")
    assert h.status_code == 200 and "calculat acum, nesalvat" in h.text
    assert "efecte/publica:facebook: esec (500) — platforma; pornit din http/POST /publicare" in h.text
    r = client.post(
        "/urme/genereaza",
        data={"csrf_token": csrf(client, "/urme?luna=2033-02"), "luna": "2033-02"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and "nesalvat" not in client.get("/urme?luna=2033-02").text
    assert client.get(f"/urme/fir/{fir}").text.count('data-rezultat="') == 2
    j = client.get("/urme/export.json?luna=2033-02")
    assert j.headers["content-type"].startswith("application/json") and j.json()["total_esecuri"] == 1
    c = list(csv.DictReader(io.StringIO(client.get("/urme/export.csv?luna=2033-02&ce=esecuri").text)))
    assert [(x["componenta"], x["sursa"], x["cod"]) for x in c] == [("efecte", "http/POST /publicare", "500")]
    ind = list(csv.DictReader(io.StringIO(client.get("/urme/export.csv?luna=2033-02&ce=indicatori").text)))
    assert {x["componenta"] for x in ind} >= {"http", "efecte"}
    toate = list(csv.DictReader(io.StringIO(client.get("/urme/export.csv?luna=2033-02&ce=urme").text)))
    assert {x["corelare_id"] for x in toate} >= {fir}
    assert client.get("/urme/export.csv?luna=2033-02&ce=altceva").status_code == 400
    assert client.get("/urme?luna=nu-e-luna").status_code == 400


def test_alte_roluri_nu_au_ecranul(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float]
) -> None:
    autentifica(client, fabrica_conturi(Rol.ANALIST, cu_totp=True), ceas)
    assert client.get("/urme").status_code == 403 and client.get("/urme/export.json").status_code == 403
    assert 'href="/urme"' not in client.get("/meniu").text
