"""F2.4 — fluxul de probă (SIMULAT) pe motorul durabil: un livrabil care eșuează mereu se oprește la limită și
ajunge la om."""

import uuid

import pytest

from app import productie
from app.db import sesiune_tenant
from app.operare import coada_erori, motor
from app.operare.notificari import Nivel
from app.productie.stari import Stare
from tests.integration import fluxuri_livrabil as proba
from tests.integration.utile_productie import AnunturiFalse, livrabil, randuri

pytestmark = pytest.mark.db


def ruleaza(tenant: uuid.UUID, lid: uuid.UUID, scenariu: str) -> str:
    job = motor.trimite(proba.proba, str(tenant), str(lid), scenariu, cheie=f"proba-{lid}")
    rez = motor.asteapta_flux(job, timeout_sec=30)
    assert rez.stare is motor.StareJob.TERMINAT, rez.eroare
    with sesiune_tenant(tenant) as db:
        liv = productie.citeste(db, lid)
        assert liv is not None
        return liv.stare


def test_livrabilul_care_esueaza_mereu_se_opreste_la_limita_si_ajunge_la_om(
    executor: None, tenant: uuid.UUID, anunturi: AnunturiFalse, admin_engine
) -> None:  # type: ignore[no-untyped-def]
    lid = livrabil(tenant)
    assert ruleaza(tenant, lid, "mereu_esueaza") == Stare.COADA_DE_ERORI.value

    istoric = [(r["din"], r["in_stare"]) for r in randuri(admin_engine, lid) if r["rezultat"] == "aplicata"]
    assert istoric == [
        (None, "planificat"),
        ("planificat", "briefat"),
        ("briefat", "in_scriere"),
        ("in_scriere", "in_validare"),
        ("in_validare", "in_reparatie"),  # runda 1
        ("in_reparatie", "in_validare"),
        ("in_validare", "in_reparatie"),  # runda 2
        ("in_reparatie", "in_validare"),
        ("in_validare", "coada_de_erori"),  # a treia: la om
    ]
    with sesiune_tenant(tenant) as db:
        liv = productie.citeste(db, lid)
        assert liv is not None
        assert (liv.runde_reparatie, liv.escaladari, liv.versiune, liv.apeluri_llm) == (2, 1, 3, 6)
        [intrare] = coada_erori.lista(db)
    assert intrare.context["de_la_componenta"] == {"verdict": "SIMULAT: hook slab", "validator": "G1"}
    assert intrare.context["limita_depasita"] == "runde_reparatie" and intrare.severitate == "major"
    assert anunturi.nivele() == [Nivel.IMPORTANT]


def test_livrabilul_cu_o_runda_de_reparatie_trece(executor: None, tenant: uuid.UUID) -> None:
    lid = livrabil(tenant)
    assert ruleaza(tenant, lid, "o_runda") == Stare.VALIDAT.value
    with sesiune_tenant(tenant) as db:
        liv = productie.citeste(db, lid)
        assert liv is not None and (liv.runde_reparatie, liv.escaladari, liv.versiune) == (1, 0, 2)
        assert coada_erori.lista(db) == []


def test_bugetul_depasit_in_flux_opreste_livrabilul(
    executor: None, tenant: uuid.UUID, anunturi: AnunturiFalse
) -> None:
    lid = livrabil(tenant)
    assert ruleaza(tenant, lid, "buget") == Stare.COADA_DE_ERORI.value
    with sesiune_tenant(tenant) as db:
        [intrare] = coada_erori.lista(db)
    assert intrare.context["limita_depasita"] == "buget_apeluri"
    assert (
        intrare.context["contoare"]["apeluri_llm"] == 51
        and intrare.context["limite"]["buget_apeluri_llm"] == 40
    )


def test_productia_oprita_lasa_livrabilul_planificat(
    executor: None, tenant: uuid.UUID, om: uuid.UUID
) -> None:
    from app.db import sesiune_agentie
    from app.operare import opriri
    from app.operare.opriri import Oprire

    lid = livrabil(tenant)
    with sesiune_agentie(om) as db:
        opriri.seteaza(db, Oprire.PRODUCTIE, True, canal="panou", utilizator_id=om)
    job = motor.trimite(proba.proba, str(tenant), str(lid), "ok", cheie=f"proba-oprita-{lid}")
    rez = motor.asteapta_flux(job, timeout_sec=30)
    assert rez.stare is motor.StareJob.TERMINAT
    with sesiune_tenant(tenant) as db:
        liv = productie.citeste(db, lid)
        assert liv is not None and liv.stare == "planificat"
