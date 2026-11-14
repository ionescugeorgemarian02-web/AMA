"""F7.6 — facturarea. „Gata când”: în mediul de probă al procesatorului, un abonament se creează, se reînnoiește și
se suspendă la neplată. Procesatorul e SIMULAT (`ProcesatorSimulat`: abonamente în proces, webhook-uri semnate
HMAC ca la procesatorul real); emailurile merg în cutia poștală SIMULATĂ."""

# ruff: noqa: F811
import datetime as dt
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.connectors import plati, registru
from app.connectors.email import CutiePostalaSimulata
from app.db import sesiune_agentie
from app.finante import abonamente
from app.finante.modele import Abonament, Factura
from app.operare import opriri
from app.site import audit
from tests.integration.conftest import csrf_din
from tests.integration.utile_site import asteapta, cutie, link_din  # noqa: F401

pytestmark = pytest.mark.db
SECRET = "secret-de-proba-webhook-0123456789"  # pragma: allowlist secret
EMAIL = "facturi@zorilor.example"


@pytest.fixture
def procesator(
    monkeypatch: pytest.MonkeyPatch, cutie: CutiePostalaSimulata
) -> Iterator[plati.ProcesatorSimulat]:
    monkeypatch.setenv("AMA_PLATI_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()
    p = plati.ProcesatorSimulat(secret=SECRET)
    registru.inregistreaza_sistem(plati.TIP, p)
    yield p
    get_settings.cache_clear()


def trimite(client: TestClient, ev: tuple[bytes, dict[str, str]]) -> str:
    r = client.post("/facturare/webhook", content=ev[0], headers=ev[1])
    assert r.status_code == 200, r.text
    return str(r.json()["rezultat"])


def abonamentul() -> Abonament:
    with sesiune_agentie() as db:
        return db.execute(select(Abonament).where(Abonament.email_facturare == EMAIL)).scalar_one()


def test_abonament_creat_reinnoit_si_suspendat_la_neplata(
    client: TestClient, procesator: plati.ProcesatorSimulat, cutie: CutiePostalaSimulata, executor: None
) -> None:
    # înscrierea din site: clientul și abonamentul; procesatorul întoarce pagina lui de plată
    h = client.get("/site/inscriere?plan=crestere").text
    assert 'value="crestere" selected' in h and "nu vedem datele cardului" in h
    r = client.post("/site/inscriere", data={"csrf_token": csrf_din(h), "firma": "Cafeneaua Zorilor", "email": EMAIL,
                    "plan": "crestere", "acord": "da", "t": audit.jeton_formular(time.time() - 10)},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    pagina_plata = r.headers["location"]

    def pagina_cu_link() -> str | None:
        t = client.get(pagina_plata).text
        return t if "Plătește" in t else None

    h = asteapta(pagina_cu_link)
    assert 'href="https://plati.example.invalid/checkout/' in h
    [sub] = procesator.abonamente
    a = abonamentul()
    assert a.stare == "in_asteptare_plata" and a.suma == 2990 and a.plan == "crestere"
    # plata pe pagina procesatorului → webhook-uri semnate: activ + prima factură
    activ, factura = procesator.plateste(sub)
    assert trimite(client, activ) == "aplicat" and trimite(client, factura) == "aplicat"
    assert trimite(client, activ) == "duplicat"
    a = abonamentul()
    assert a.stare == "activ" and a.id_extern == sub and a.perioada_pana_la is not None
    assert "Plata a fost primită" in client.get(pagina_plata).text
    invitatie = asteapta(lambda: next((m for m in cutie.catre(EMAIL) if "Activează" in m.subiect), None))
    assert "/portal/activare/" in invitatie.text
    # webhook fals: semnătură greșită sau prea vechi
    corp, antete = procesator.reinnoieste(sub, reusita=True)
    assert (
        client.post(
            "/facturare/webhook", content=corp, headers={**antete, "x-semnatura": "t=1,v1=00"}
        ).status_code
        == 400
    )
    vechi = plati.semneaza(corp, SECRET, t=int(time.time()) - 3600)
    assert (
        client.post("/facturare/webhook", content=corp, headers={**antete, "x-semnatura": vechi}).status_code
        == 400
    )
    # reînnoirea automată reușită
    perioada_1 = a.perioada_pana_la
    assert trimite(client, (corp, antete)) == "aplicat"
    a = abonamentul()
    assert a.stare == "activ" and a.perioada_pana_la is not None and perioada_1 is not None
    assert a.perioada_pana_la > perioada_1
    # reînnoirea eșuată: restant, anunț, 7 zile de grație; apoi suspendat, producția oprită, datele rămân
    assert trimite(client, procesator.reinnoieste(sub, reusita=False)) == "aplicat"
    a = abonamentul()
    assert a.stare == "restant" and a.restant_de_la is not None
    asteapta(lambda: next((m for m in cutie.catre(EMAIL) if "nu a trecut" in m.subiect), None))
    assert abonamente.verifica_restante(acum=a.restant_de_la + dt.timedelta(days=6)) == []
    assert abonamente.verifica_restante(acum=a.restant_de_la + dt.timedelta(days=8)) == [a.id]
    a = abonamentul()
    with sesiune_agentie() as db:
        assert a.stare == "suspendat" and opriri.este_oprit(db, opriri.Oprire.CLIENT, tenant_id=a.tenant_id)
        assert [f.stare for f in db.execute(select(Factura).where(Factura.abonament_id == a.id).order_by(
            Factura.creat_la)).scalars()] == ["platita", "platita", "esuata"]  # fmt: skip
    # plata ulterioară reactivează și ridică oprirea
    assert trimite(client, procesator.reinnoieste(sub, reusita=True)) == "aplicat"
    with sesiune_agentie() as db:
        assert abonamentul().stare == "activ"
        assert not opriri.este_oprit(db, opriri.Oprire.CLIENT, tenant_id=a.tenant_id)


def test_semnatura_nucleu() -> None:
    corp = b'{"id":"evt_1"}'
    antet = plati.semneaza(corp, "x" * 20, t=1000)
    assert antet.startswith("t=1000,v1=") and len(antet.split("v1=")[1]) == 64
