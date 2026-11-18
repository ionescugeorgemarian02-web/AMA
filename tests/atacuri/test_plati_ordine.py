"""Atac F15.2 (MEDIU în revizie): evenimentele de plată sosite în altă ordine (sau reluate de un atacator cu
o semnătură veche validă) nu fac un client plătitor restant și nu scurtează perioada plătită."""

import datetime as dt
import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.connectors import plati
from app.db import sesiune_agentie
from app.finante.modele import Abonament
from app.site import audit
from tests.integration.conftest import csrf_din
from tests.integration.utile_site import asteapta

pytestmark = pytest.mark.db
EMAIL = "plati-ordine@zorilor.example"  # propriu: abonamentele din alte teste rămân în baza comună


def abonamentul() -> Abonament:
    with sesiune_agentie() as db:
        return db.execute(select(Abonament).where(Abonament.email_facturare == EMAIL)).scalar_one()


def _post(client: TestClient, ev: tuple[bytes, dict[str, str]]) -> str:
    r = client.post("/facturare/webhook", content=ev[0], headers=ev[1])
    assert r.status_code == 200, r.text
    return str(r.json()["rezultat"])


def test_esecul_tarziu_al_unei_facturi_platite_si_activarea_veche_nu_strica_abonamentul(
    client: TestClient, procesator: plati.ProcesatorSimulat, executor: None
) -> None:
    h = client.get("/site/inscriere?plan=crestere").text
    client.post("/site/inscriere", data={"csrf_token": csrf_din(h), "firma": "Firma Ordine", "email": EMAIL,
                "plan": "crestere", "acord": "da", "t": audit.jeton_formular(time.time() - 10)},
                follow_redirects=False)  # fmt: skip
    asteapta(lambda: procesator.abonamente or None)
    [sub] = procesator.abonamente
    a_sim = procesator.abonamente[sub]
    activ, factura = procesator.plateste(sub)
    assert _post(client, activ) == "aplicat" and _post(client, factura) == "aplicat"
    pana_la = abonamentul().perioada_pana_la
    f = json.loads(factura[0])
    esec = procesator._eveniment("factura.esuata", a_sim, factura=f["factura"], suma=f["suma"], moneda="RON",
                                 perioada_de_la=f["perioada_de_la"], perioada_pana_la=f["perioada_pana_la"])  # fmt: skip
    assert _post(client, esec) == "ignorat"
    vechi = procesator._eveniment(
        "abonament.activ",
        a_sim,
        perioada_pana_la=(dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).isoformat(),
    )
    assert _post(client, vechi) == "aplicat"
    a = abonamentul()
    assert a.stare == "activ" and a.restant_de_la is None
    assert a.perioada_pana_la == pana_la, "evenimentul vechi nu scurtează perioada plătită"
