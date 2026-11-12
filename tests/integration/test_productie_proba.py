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


def test_livrabilul_cu_o_runda_de_reparatie_trece_si_asteapta_aprobarea(
    executor: None, tenant: uuid.UUID
) -> None:
    lid = livrabil(tenant)
    assert ruleaza(tenant, lid, "o_runda") == Stare.ASTEAPTA_APROBARE.value
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


# --- aprobare și expirare, cap-coadă pe motorul durabil (F2.8) ----------------------------------------------------


def ruleaza_din_nou(tenant: uuid.UUID, lid: uuid.UUID, scenariu: str, eticheta: str) -> str:
    job = motor.trimite(proba.proba, str(tenant), str(lid), scenariu, cheie=f"proba-{eticheta}-{lid}")
    assert motor.asteapta_flux(job, timeout_sec=30).stare is motor.StareJob.TERMINAT
    with sesiune_tenant(tenant) as db:
        liv = productie.citeste(db, lid)
        assert liv is not None
        return liv.stare


def aproba_cererea(tenant: uuid.UUID, lid: uuid.UUID, om: uuid.UUID) -> None:
    from app.conturi import Rol
    from app.productie import aprobari

    with sesiune_tenant(tenant, om) as db:
        ap = aprobari.cerere_activa(db, lid)
        assert ap is not None
        r = aprobari.decide(db, ap.id, productie.Hotarare.APROBAT, utilizator_id=om, rol=Rol.OPERATOR)
        assert r.aplicat


def test_un_text_aprobat_de_om_parcurge_drumul_pana_la_inchis(
    executor: None, tenant: uuid.UUID, om: uuid.UUID, admin_engine
) -> None:  # type: ignore[no-untyped-def]
    lid = livrabil(tenant)
    assert ruleaza(tenant, lid, "ok") == Stare.ASTEAPTA_APROBARE.value, "fluxul se oprește și așteaptă un om"
    aproba_cererea(tenant, lid, om)
    assert ruleaza_din_nou(tenant, lid, "ok", "dupa") == Stare.INCHIS.value
    parcurse = [r["in_stare"] for r in randuri(admin_engine, lid) if r["rezultat"] == "aplicata"]
    assert parcurse == [
        "planificat",
        "briefat",
        "in_scriere",
        "in_validare",
        "validat",
        "asteapta_aprobare",
        "aprobat",
        "programat",
        "in_publicare",
        "publicat",
        "in_masurare",
        "inchis",
    ]


def test_un_video_parcurge_toate_cele_16_stari_normale(
    executor: None, tenant: uuid.UUID, om: uuid.UUID, admin_engine
) -> None:  # type: ignore[no-untyped-def]
    lid = livrabil(tenant, tip="video")
    assert ruleaza(tenant, lid, "o_runda") == Stare.ASTEAPTA_APROBARE.value
    aproba_cererea(tenant, lid, om)
    assert ruleaza_din_nou(tenant, lid, "o_runda", "dupa") == Stare.INCHIS.value
    parcurse = {r["in_stare"] for r in randuri(admin_engine, lid) if r["rezultat"] == "aplicata"}
    assert parcurse == {s.value for s in productie.NORMALE}, (
        "toate cele 16 stări normale, în ordinea din tabel"
    )


def test_aprobarea_neprimita_la_timp_expira_prin_jobul_programat_nu_se_publica(
    executor: None, tenant: uuid.UUID, admin_engine
) -> None:  # type: ignore[no-untyped-def]
    import datetime as dt
    import time

    from app.productie import fluxuri

    slot = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=2.5)  # slotul de publicare e aproape
    lid = livrabil(tenant, termen_la=slot)
    assert ruleaza(tenant, lid, "ok") == Stare.ASTEAPTA_APROBARE.value
    time.sleep(max(0.0, (slot - dt.datetime.now(dt.UTC)).total_seconds()) + 0.3)  # nimeni nu aprobă
    job = motor.trimite(fluxuri.tic, dt.datetime.now(dt.UTC), None)
    assert motor.asteapta_flux(job, timeout_sec=30).stare is motor.StareJob.TERMINAT
    with sesiune_tenant(tenant) as db:
        liv = productie.citeste(db, lid)
        assert liv is not None and liv.stare == "expirat"
    parcurse = [r["in_stare"] for r in randuri(admin_engine, lid) if r["rezultat"] == "aplicata"]
    assert parcurse[-2:] == ["asteapta_aprobare", "expirat"]
    assert not {"aprobat", "programat", "in_publicare", "publicat"} & set(parcurse)
    # fluxul reluat nu publică nimic: un livrabil expirat nu e „activ”
    assert ruleaza_din_nou(tenant, lid, "ok", "dupa") == Stare.EXPIRAT.value
