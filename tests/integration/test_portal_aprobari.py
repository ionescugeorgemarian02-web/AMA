"""F7.4 — portalul: Creier, calendar, aprobări. „Gata când”: clientul de test aprobă un lot de pe telefon.
Cererile ajung la client pentru că are un utilizator care poate aproba (19.4); textele sunt ale modelului FALS
(brandul FICTIV), validarea e cascada reală deterministă. Telefonul real: la migrare."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app import continut, productie, publicare
from app.conturi import Rol
from app.db import sesiune_tenant
from app.productie import Stare
from tests.continut_utile import model_postari
from tests.integration.conftest import Cont, csrf_din, login
from tests.integration.lant_continut import cu_briefuri, fara_cereri_ramase  # noqa: F401
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fara_cereri_ramase")]


def lot_la_client(tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, n: int = 3) -> list[uuid.UUID]:
    cal, _ = cu_briefuri(tenant, om, modele)
    model_postari(modele)
    with sesiune_tenant(tenant) as db:
        lids = [
            i.livrabil_id for i in continut.calendar.intrari(db, cal) if i.tip == "postare" and i.livrabil_id
        ]
    lids = lids[:n]
    for lid in lids:
        assert continut.pipeline.produ(tenant, lid) == Stare.ASTEAPTA_APROBARE.value
    return lids


def test_clientul_aproba_un_lot_de_pe_telefon(
    client: TestClient, fabrica_conturi: Callable[..., Cont], tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals,
    executor: None,
) -> None:  # fmt: skip
    titular = fabrica_conturi(Rol.CLIENT_TITULAR, tenant_id=tenant)
    lids = lot_la_client(tenant, om, modele)
    with sesiune_tenant(tenant) as db:
        cereri = [productie.aprobari.cerere_activa(db, lid) for lid in lids]
        assert all(c is not None and c.decident == productie.Decident.CLIENT.value for c in cereri)
    assert login(client, titular.email, titular.parola).status_code == 303
    h = client.get("/portal/aprobari").text
    assert 'name="viewport"' in h and f"Aprobă tot lotul ({len(lids)})" in h
    assert h.count('action="/portal/aprobari/lot"') == 1 and h.count('name="cerere"') == len(lids)
    assert "Cafeneaua Zorilor" in h or "cafea" in h.lower()  # previzualizarea textului real
    assert "Ce urmează" in client.get("/portal/calendar").text
    assert "Brieful firmei" in client.get("/portal/creier").text
    # o atingere: tot lotul
    r = client.post("/portal/aprobari/lot", data={"csrf_token": csrf_din(h), "cerere": [
        f"{c.id}:{c.versiune}" for c in cereri if c is not None]}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"] == "/portal/aprobari?mesaj=lot"
    with sesiune_tenant(tenant) as db:
        for lid in lids:
            lv = productie.citeste(db, lid)
            assert lv is not None and lv.stare == Stare.PROGRAMAT.value  # aprobat → pachetul de publicare
            [ap] = [a for a in productie.aprobari.ale_livrabilului(db, lid) if a.stare == "aprobat"]
            assert ap.decis_de == titular.id and ap.versiune == lv.versiune
            assert publicare.asistata.ale_livrabilului(db, lid)
    assert "Nimic de aprobat acum" in client.get("/portal/aprobari").text


def test_lot_cu_versiune_veche_nu_se_aproba_si_vizitatorul_nu_poate(
    client: TestClient, fabrica_conturi: Callable[..., Cont], tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals,
    executor: None,
) -> None:  # fmt: skip
    fabrica_conturi(Rol.CLIENT_TITULAR, tenant_id=tenant)
    [lid] = lot_la_client(tenant, om, modele, n=1)
    vizitator = fabrica_conturi(Rol.CLIENT_VIZITATOR, tenant_id=tenant)
    with sesiune_tenant(tenant) as db:
        c = productie.aprobari.cerere_activa(db, lid)
        assert c is not None
    assert login(client, vizitator.email, vizitator.parola).status_code == 303
    h = client.get("/portal/aprobari").text
    assert "Aprobă tot lotul" not in h
    r = client.post(
        "/portal/aprobari/lot",
        data={
            "csrf_token": csrf_din(client.get("/portal/onboarding").text),
            "cerere": f"{c.id}:{c.versiune}",
        },
    )
    assert r.status_code == 403
    client.cookies.clear()
    aprobator = fabrica_conturi(Rol.CLIENT_APROBATOR, tenant_id=tenant)
    assert login(client, aprobator.email, aprobator.parola).status_code == 303
    h = client.get("/portal/aprobari").text
    r = client.post(
        "/portal/aprobari/lot", data={"csrf_token": csrf_din(h), "cerere": f"{c.id}:{c.versiune + 1}"}
    )
    assert r.status_code == 200 and "nu a fost aprobat" in r.text
    with sesiune_tenant(tenant) as db:
        lv = productie.citeste(db, lid)
        assert lv is not None and lv.stare == Stare.ASTEAPTA_APROBARE.value
