"""F9.9 — site și blog (H6). „Gata când”: un articol aprobat din F7.10 apare pe blogul agenției, cu
verificările on-page trecute. Articolul trece prin aprobare, programare și executorul de efecte (blogul
găzduit e real; CMS-ul clientului, WordPress, e SIMULAT în testul de contract). Modelul e FALS (# SIMULAT),
ca în F7.10."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app import productie, seo
from app.connectors import registru
from app.connectors.publicare.blog import ConectorBlog
from app.conturi import Rol
from app.db import sesiune_tenant
from app.operare import efecte
from app.productie import Hotarare
from app.publicare import blog, programare
from tests.integration.publicare_utile import livrabil_stare
from tests.integration.test_seo_articole import CUVINTE, SURSE, scriptat
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401

pytestmark = pytest.mark.db


@pytest.fixture
def conector_blog() -> Iterator[None]:
    registru.uita_tot()
    registru.inregistreaza("blog", ConectorBlog())
    yield
    registru.uita_tot()


def test_articolul_aprobat_apare_pe_blogul_agentiei_cu_on_page_trecut(
    client: TestClient,
    tenant: uuid.UUID,
    om: uuid.UUID,
    modele: ModelFals,
    conector_blog: None,
    admin_engine: Engine,
) -> None:
    scriptat(modele)
    g = seo.cuvinte.grupeaza(CUVINTE)[0]
    with sesiune_tenant(tenant, om) as db:
        blog.configureaza_gazduit(db, tenant, utilizator_id=om)
        r = seo.articole.scrie(db, tenant, g, SURSE, publica=False)
        assert r["on_page"] == [] and r["validare"] and not r["publicat"]
        lid = blog.pregateste(db, tenant, r, utilizator_id=om)
    with (
        admin_engine.begin() as c
    ):  # blogul agenției e comun bazei de test: alt test poate să fi publicat adresa
        c.execute(text("DELETE FROM site_articole WHERE slug = :s"), {"s": r["slug"]})
    assert client.get(f"/site/blog/{r['slug']}").status_code == 404, "nimic pe blog înainte de aprobare"
    assert livrabil_stare(tenant, lid) == "asteapta_aprobare"
    with sesiune_tenant(tenant) as db:
        ap = productie.aprobari.cerere_activa(db, lid)
        assert ap is not None
        productie.aprobari.decide(
            db, ap.id, Hotarare.APROBAT, utilizator_id=om, rol=Rol.PROPRIETAR, versiune=1
        )
    # aprobarea l-a programat singură (canalul blog: automat, fără aprobare de platformă)
    with sesiune_tenant(tenant) as db:
        [p] = programare.a_livrabilului(db, lid)
    assert livrabil_stare(tenant, lid) == "programat"
    assert programare.tic_acum(p.la + dt.timedelta(seconds=1)) == {"plecat": 1}
    with sesiune_tenant(tenant) as db:
        [p] = programare.a_livrabilului(db, lid)
        assert p.efect_id is not None
    assert efecte.incearca_efect(tenant, p.efect_id) == "trimis"
    assert livrabil_stare(tenant, lid) == "publicat"
    h = client.get(f"/site/blog/{r['slug']}").text
    assert (
        r["titlu"] in h
        and "Surse" in h
        and "https://example.org/incredere" in h
        and "example.org/altceva" not in h
    )
    assert f'href="/site/blog/{r["slug"]}"' in client.get("/site/blog").text
