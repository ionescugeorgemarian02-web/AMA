"""F2.4 — partea din panou: butonul „Producția nouă”, intrarea unui livrabil oprit la limită în ecranul Alerte,
jobul programat al întrerupătorului."""

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app import productie
from app.conturi import Rol
from app.db import sesiune_agentie, sesiune_tenant
from app.operare import motor, opriri
from app.operare.opriri import Oprire
from app.productie import fluxuri
from app.productie.stari import Stare
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import livrabil, muta

pytestmark = pytest.mark.db
Fabrica = Callable[..., Cont]


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


def livrabil_oprit_la_limita(tenant: uuid.UUID) -> uuid.UUID:
    lid = livrabil(tenant)
    curenta = Stare.PLANIFICAT
    for s in (Stare.BRIEFAT, Stare.IN_SCRIERE, Stare.IN_VALIDARE):
        muta(tenant, lid, curenta, s)
        curenta = s
    for _ in range(2):
        muta(tenant, lid, Stare.IN_VALIDARE, Stare.IN_REPARATIE)
        muta(tenant, lid, Stare.IN_REPARATIE, Stare.IN_VALIDARE)
    muta(tenant, lid, Stare.IN_VALIDARE, Stare.IN_REPARATIE, detalii={"verdict": "ton nepotrivit"})
    return lid


# --- butonul de oprire a producției noi ---------------------------------------------------------------------


def test_butonul_productia_noua_opreste_si_repornirea_cere_confirmare(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, admin_engine: Engine
) -> None:
    acasa = client.get("/").text
    assert "Producția nouă (global)" in acasa
    r = client.post(
        "/opriri/opreste",
        data={"tip": "productie", "motiv": "verificare", "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with sesiune_agentie() as db:
        rand = opriri.citeste(db, Oprire.PRODUCTIE)
        assert rand is not None and rand.activ and rand.canal == "panou" and rand.schimbat_de == proprietar.id
    lid = livrabil(tenant)
    with pytest.raises(productie.ProductieOprita), sesiune_tenant(tenant) as db:
        productie.muta(db, lid, Stare.PLANIFICAT, Stare.BRIEFAT, componenta="D5")
    # repornirea cere confirmare și o face omul
    assert "Producția nouă" in client.get("/opriri/confirma-pornire?tip=productie").text
    r = client.post(
        "/opriri/porneste",
        data={"tip": "productie", "confirmare": "da", "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert muta(tenant, lid, Stare.PLANIFICAT, Stare.BRIEFAT).aplicat
    with admin_engine.connect() as c:
        a = c.execute(
            text(
                "SELECT utilizator_id FROM jurnal_audit WHERE actiune = 'oprire.repornit' AND obiect_id = 'productie' "
                "ORDER BY id DESC LIMIT 1"
            )
        ).scalar_one()
    assert a == proprietar.id


# --- ecranul Alerte arată livrabilul oprit la limită ----------------------------------------------------------


def test_alerta_unui_livrabil_oprit_arata_diagnosticul_si_nu_ofera_reia(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID
) -> None:
    lid = livrabil_oprit_la_limita(tenant)
    html = client.get("/alerte").text
    assert "livrabil" in html and "Major" in html
    with sesiune_agentie() as db:
        from app.operare.coada_erori import dupa_cheie

        intrare = dupa_cheie(db, f"livrabil:{lid}:1")
    assert intrare is not None and f"/alerte/{intrare.id}" in html
    detaliu = client.get(f"/alerte/{intrare.id}")
    assert detaliu.status_code == 200
    h = detaliu.text
    assert "Diagnostic: livrabil oprit la o limită" in h and str(lid) in h
    assert "limita de runde de reparație" in h and "ton nepotrivit" in h
    assert "2/2" in h and "in_reparatie" in h
    assert f'action="/alerte/{intrare.id}/reia"' not in h, "nu există job de reluat"
    assert f'action="/alerte/{intrare.id}/inchide"' in h
    r = client.post(f"/alerte/{intrare.id}/reia", data={"csrf_token": csrf(client)})
    assert r.status_code == 409 and "Producție" in r.text
    r = client.post(
        f"/alerte/{intrare.id}/inchide",
        data={"motiv": "văzut, reluăm mâine", "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303


# --- jobul programat -------------------------------------------------------------------------------------------


def test_jobul_programat_la_minut_evalueaza_intrerupatorul(
    executor: None, tenant: uuid.UUID, admin_engine: Engine
) -> None:
    with admin_engine.begin() as c:
        c.execute(text("ALTER TABLE livrabile_tranzitii DISABLE TRIGGER USER"))
        c.execute(text("TRUNCATE livrabile_tranzitii"))
        c.execute(text("ALTER TABLE livrabile_tranzitii ENABLE TRIGGER USER"))
    for _ in range(10):
        lid = livrabil(tenant)
        muta(tenant, lid, Stare.PLANIFICAT, Stare.BRIEFAT)
        muta(tenant, lid, Stare.BRIEFAT, Stare.IN_SCRIERE)
        muta(tenant, lid, Stare.IN_SCRIERE, Stare.COADA_DE_ERORI)
    job = motor.trimite(fluxuri.tic, dt.datetime.now(dt.UTC), None, coada=motor.Coada.IO)
    rez = motor.asteapta_flux(job, timeout_sec=30)
    assert rez.stare is motor.StareJob.TERMINAT
    with sesiune_agentie() as db:
        assert opriri.este_oprit(db, Oprire.PRODUCTIE)


def test_programarea_si_modulul_sunt_inregistrate_in_worker() -> None:
    from app import worker

    fluxuri.declara_programari()
    [p] = [p for p in motor.programari_declarate() if p.nume == fluxuri.NUME_TIC]
    assert p.cron == "0 * * * * *", "la minut (secunda 0)"
    assert p.flux == "productie.tic"
    assert "app.productie.fluxuri" in worker.MODULE_FLUXURI
