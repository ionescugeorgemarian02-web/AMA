"""F15.1, docs/25 §25.3: un webhook sosește de două ori (și chiar simultan) -> este procesat o singură dată.

Procesatorul de plăți e SIMULAT (`ProcesatorSimulat`, ca în test_facturare); webhook-urile sunt semnate real."""

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.connectors import plati
from app.db import sesiune_agentie
from app.finante.modele import Factura
from app.site import audit
from tests.integration.conftest import csrf_din
from tests.integration.test_facturare import EMAIL, abonamentul, procesator  # noqa: F401
from tests.integration.utile_site import asteapta, cutie  # noqa: F401

pytestmark = pytest.mark.db


def _post(client: TestClient, ev: tuple[bytes, dict[str, str]]) -> str:
    r = client.post("/facturare/webhook", content=ev[0], headers=ev[1])
    return str(r.json()["rezultat"]) if r.status_code == 200 else f"http_{r.status_code}"


def test_webhookul_de_plata_repetat_se_aplica_o_singura_data(
    client: TestClient,
    procesator: plati.ProcesatorSimulat,  # noqa: F811
    executor: None,
) -> None:
    h = client.get("/site/inscriere?plan=crestere").text
    client.post("/site/inscriere", data={"csrf_token": csrf_din(h), "firma": "Cafeneaua Zorilor", "email": EMAIL,
                "plan": "crestere", "acord": "da", "t": audit.jeton_formular(time.time() - 10)},
                follow_redirects=False)  # fmt: skip
    asteapta(lambda: procesator.abonamente or None)
    [sub] = procesator.abonamente
    activ, factura = procesator.plateste(sub)
    assert _post(client, activ) == "aplicat"
    # aceeași factură, livrată de patru ori simultan (procesatorul reîncearcă) și încă o dată după
    with ThreadPoolExecutor(4) as ex:
        rezultate = list(ex.map(lambda _: _post(client, factura), range(4)))
    rezultate.append(_post(client, factura))
    assert rezultate.count("aplicat") == 1, rezultate
    assert all(r in ("aplicat", "duplicat") or r.startswith("http_5") for r in rezultate), rezultate
    a = abonamentul()
    with sesiune_agentie() as db:
        n = db.execute(
            select(func.count()).select_from(Factura).where(Factura.abonament_id == a.id)
        ).scalar_one()
    assert n == 1 and a.stare == "activ"
