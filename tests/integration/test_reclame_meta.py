"""F13.1 — citirea rezultatelor Meta. „Gata când”: cifrele contului agenției apar în panou și coincid cu
managerul de reclame. Marketing API e SIMULAT (contract HTTP local, # SIMULAT)."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.conturi import Rol
from app.db import sesiune_agentie
from app.panou.reclame_web import lei
from app.reclame import rezultate
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica
from tests.integration.utile_productie import fabrica_clienti  # noqa: F401
from tests.integration.utile_reclame import ACUM, AZI, autorizeaza, cont_agentie, depozit, meta  # noqa: F401
from tests.platforme.meta_ads import MarketingSimulat

pytestmark = pytest.mark.db
Fabrica = Callable[..., tuple[uuid.UUID, uuid.UUID]]


def test_cifrele_contului_agentiei_apar_in_panou_si_coincid_cu_managerul(
    meta: MarketingSimulat,
    depozit: object,
    cont_agentie: Fabrica,
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
) -> None:
    tenant, cont_id = cont_agentie()
    autorizeaza(depozit, meta, tenant)  # type: ignore[arg-type]
    a = meta.adauga_campanie("Audit gratuit – căutare", 3_000)
    b = meta.adauga_campanie("Audit gratuit – retargetare", 2_000)
    for i in range(10):
        meta.zi(AZI - dt.timedelta(days=i), ritm=0.9 + i / 100)
    meta.obiecte[b]["status"] = "PAUSED"
    meta.zi(AZI - dt.timedelta(days=40))  # în afara primei citiri (30 de zile)

    assert rezultate.citeste_cont(cont_id, ACUM).startswith("citit:")
    t30 = meta.manager(AZI - dt.timedelta(days=29), AZI)
    with sesiune_agentie() as db:
        t = rezultate.totaluri(db, cont_id, AZI - dt.timedelta(days=29), AZI)
        pe_campanii = {
            e: x for e, _, x in rezultate.pe_obiecte(db, cont_id, AZI - dt.timedelta(days=29), AZI)
        }
        pe_reclame = rezultate.pe_obiecte(db, cont_id, AZI - dt.timedelta(days=29), AZI, nivel="reclama")
    assert (t.cheltuiala_bani, t.afisari, t.clicuri, t.rezultate) == (
        t30["bani"],
        t30["afisari"],
        t30["clicuri"],
        t30["rezultate"],
    )
    assert set(pe_campanii) == {a, b} and len(pe_reclame) == 2, "campaniile și reclamele, fiecare o dată"
    assert t.rezultate > 0 and t.cost_pe_rezultat_bani is not None

    # platforma corectează ziua de ieri după atribuire: recitirea o înlocuiește, nu o dublează
    ad_a = meta.reclame(a)[0]["id"]
    meta.inregistreaza(ad_a, AZI - dt.timedelta(days=1), bani=0, afisari=0, clicuri=0, rezultate=3)
    assert rezultate.citeste_cont(cont_id, ACUM + dt.timedelta(hours=1)).startswith("citit:")
    with sesiune_agentie() as db:
        assert (
            rezultate.totaluri(db, cont_id, AZI - dt.timedelta(days=29), AZI).rezultate
            == t30["rezultate"] + 3
        )

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    h = client.get("/reclame").text
    assert "Agenția – cont de test" in h and "contul agenției" in h
    h = client.get(f"/reclame/cont/{cont_id}").text
    assert f'<td data-camp="cheltuiala">{lei(t30["bani"])} RON</td>' in h
    assert f'<td data-camp="rezultate">{t30["rezultate"] + 3}</td>' in h
    assert f'data-campanie="{a}"' in h and f'data-campanie="{b}"' in h
    assert "/reclame" in client.get("/meniu").text


def test_fara_token_citirea_nu_scrie_nimic_si_spune_de_ce(
    meta: MarketingSimulat, cont_agentie: Fabrica
) -> None:
    _, cont_id = cont_agentie()
    meta.adauga_campanie("Fără token", 1_000)
    meta.zi(AZI)
    assert rezultate.citeste_cont(cont_id, ACUM) == "autentificare"
    with sesiune_agentie() as db:
        assert rezultate.totaluri(db, cont_id, AZI, AZI).cheltuiala_bani == 0
        c = db.get(rezultate.ContReclame, cont_id)
        assert c is not None and c.citit_la is None and "nu este autorizat" in (c.eroare_citire or "")


def test_eroarea_temporara_amana_citirea(
    meta: MarketingSimulat, depozit: object, cont_agentie: Fabrica
) -> None:
    tenant, cont_id = cont_agentie()
    autorizeaza(depozit, meta, tenant)  # type: ignore[arg-type]
    meta.injecteaza("temporar")
    assert rezultate.citeste_cont(cont_id, ACUM) == "amanat"
    assert rezultate.citeste_cont(cont_id, ACUM) == "citit:0"


def test_cont_cu_plafoane_incoerente_e_refuzat(fabrica_clienti: Callable[[], uuid.UUID]) -> None:
    with sesiune_agentie() as db, pytest.raises(rezultate.ContInvalid):
        rezultate.adauga_cont(
            db,
            tenant_id=fabrica_clienti(),
            platforma="meta",
            cont_extern="act_9",
            nume="Greșit",
            plafon_zilnic_bani=100,
            plafon_lunar_bani=50,
            plafon_campanie_bani=100,
        )
