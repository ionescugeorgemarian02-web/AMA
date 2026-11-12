"""F3.11 — planificatorul de capacitate (A4), pe Postgres real. „Gata când”: la un calendar de probă care depășește cota zilei,
livrabilele cu termen îndepărtat sunt amânate, cele cu termen apropiat rămân neatinse și o alertă spune ce nu a încăput;
„amânat” are efect real asupra livrabilului (`productie.muta` îl refuză până la `nu_inainte_de`)."""

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

from app import planificare, productie
from app.db import sesiune_agentie, sesiune_tenant
from app.operare import motor
from app.operare.motor import Coada
from app.planificare import fluxuri
from app.productie import Stare
from tests.gateway_utile import FabricaModele
from tests.integration.utile_productie import AnunturiFalse

pytestmark = pytest.mark.db
TIP = "postare_proba"


@pytest.fixture
def cost_proba(admin_engine: Engine) -> Iterator[None]:
    with admin_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO planificare_costuri (tip, profiluri, minute_cpu) VALUES (:t, "
                '\'{"creatie": {"apeluri": 2, "tokeni": 1000}}\'::jsonb, 0)'
            ),
            {"t": TIP},
        )
    yield
    with admin_engine.begin() as c:
        c.execute(text("DELETE FROM planificare_costuri WHERE tip = :t"), {"t": TIP})


@pytest.fixture
def cota_creatie(
    admin_engine: Engine, fabrica_modele: FabricaModele, cost_proba: None, cheie_proba: str
) -> Iterator[int]:
    """Profilul `creatie` cu un singur model, care mai poate face azi 13 apeluri (90% din 15, rezerva P0 rămâne)."""
    model = fabrica_modele.model(fabrica_modele.furnizor(), identificator="plan", nivel="T2", cereri_zi=15)
    with admin_engine.connect() as c:
        original = c.execute(text("SELECT lant FROM gateway_profiluri WHERE nume = 'creatie'")).scalar_one()
    with admin_engine.begin() as c:
        c.execute(text("UPDATE gateway_profiluri SET lant = :l WHERE nume = 'creatie'"), {"l": [model.cod]})
    yield 13
    with admin_engine.begin() as c:
        c.execute(
            text("UPDATE gateway_profiluri SET lant = :l WHERE nume = 'creatie'"), {"l": list(original)}
        )


def creeaza(tenant: uuid.UUID, ore: float | None) -> uuid.UUID:
    termen = None if ore is None else dt.datetime.now(dt.UTC) + dt.timedelta(hours=ore)
    with sesiune_tenant(tenant) as db:
        return productie.creeaza(db, tenant_id=tenant, tip=TIP, canal="facebook", termen_la=termen).id


def nu_inainte_de(admin: Engine, livrabil: uuid.UUID) -> dt.datetime | None:
    with admin.connect() as c:
        return c.execute(
            text("SELECT nu_inainte_de FROM livrabile WHERE id = :i"), {"i": livrabil}
        ).scalar_one()  # type: ignore[no-any-return]


def test_calendarul_de_proba_peste_cota_zilei_amana_termenele_indepartate_si_lasa_neatinse_pe_cele_apropiate(
    tenant: uuid.UUID, cota_creatie: int, anunturi: AnunturiFalse, admin_engine: Engine
) -> None:
    # 4 livrabile cu termen apropiat (între 10 și 40 de ore) și 7 cu termene între 5 și 11 zile: 22 de apeluri față de 13
    apropiate = [creeaza(tenant, ore) for ore in (10, 30, 36, 40)]
    departe = {zile: creeaza(tenant, zile * 24) for zile in (5, 6, 7, 8, 9, 10, 11)}
    plan = planificare.planifica(clienti=[tenant])
    amanate = set(plan.amanate)
    # încap 6 livrabile (12 apeluri): cele 4 protejate + cele două cu termenele cele mai apropiate dintre cele îndepărtate
    assert amanate == {departe[z] for z in (7, 8, 9, 10, 11)}
    assert all(nu_inainte_de(admin_engine, i) is None for i in apropiate)  # neatinse
    assert nu_inainte_de(admin_engine, departe[5]) is None and nu_inainte_de(admin_engine, departe[6]) is None
    for z in (7, 8, 9, 10, 11):
        assert nu_inainte_de(admin_engine, departe[z]) == planificare.sfarsit_zi(dt.datetime.now(dt.UTC))
    assert plan.rezultat.depasiri == (("apeluri", "creatie"),) and not plan.peste_capacitate
    # o alertă spune ce nu a încăput
    assert anunturi.titluri() == ["Capacitate: 5 livrabile amânate"]
    text_alerta = anunturi.trimise[0][2]
    assert "5 livrabile nu au încăput" in text_alerta and "cerut 22, disponibil 13" in text_alerta
    assert plan.alerta.startswith("5 livrabile")
    # decizia se scrie: planul zilei și câte o decizie pe livrabil
    with admin_engine.connect() as c:
        rand = c.execute(
            text(
                "SELECT livrabile, pastrate, amanate, protejate_peste_capacitate FROM planificare_planuri WHERE zi = :z"
            ),
            {"z": dt.datetime.now(dt.UTC).date()},
        ).one()
        decizii = dict(
            c.execute(
                text("SELECT livrabil_id, decizie FROM planificare_decizii WHERE tenant_id = :t"),
                {"t": tenant},
            ).all()
        )
    assert tuple(rand)[2] == 5 and rand[3] is False
    assert sorted(decizii.values()).count("amanat") == 5 and sorted(decizii.values()).count("protejat") == 4
    assert decizii[departe[5]] == "pastrat"


def test_amanarea_are_efect_real_muta_refuza_pornirea_pana_la_nu_inainte_de(
    tenant: uuid.UUID, cota_creatie: int, anunturi: AnunturiFalse, admin_engine: Engine
) -> None:
    apropiate = [creeaza(tenant, 20) for _ in range(5)]  # 10 apeluri protejate
    departe = [creeaza(tenant, zile * 24) for zile in (6, 7, 8)]  # nu încape decât unul (încă 2 apeluri)
    plan = planificare.planifica(clienti=[tenant])
    assert set(plan.amanate) == {departe[1], departe[2]}
    with sesiune_tenant(tenant) as db, pytest.raises(productie.TranzitieNepermisa) as exc:
        productie.muta(db, departe[2], Stare.PLANIFICAT, Stare.BRIEFAT, componenta="D5")
    assert exc.value.cod == "amanat" and "amânat până la" in str(exc.value)
    with sesiune_tenant(tenant) as db:  # refuzul stă în istoric
        refuzuri = [t for t in productie.istoric(db, departe[2]) if t.rezultat == "refuzata"]
    assert len(refuzuri) == 1 and refuzuri[0].detalii == {"cod": "amanat"}
    for i in (*apropiate, departe[0]):  # cele neamânate pornesc normal
        with sesiune_tenant(tenant) as db:
            assert productie.muta(db, i, Stare.PLANIFICAT, Stare.BRIEFAT, componenta="D5").aplicat
    # a trecut momentul: livrabilul amânat pornește
    with admin_engine.begin() as c:
        c.execute(
            text("UPDATE livrabile SET nu_inainte_de = now() - interval '1 minute' WHERE id = :i"),
            {"i": departe[2]},
        )
    with sesiune_tenant(tenant) as db:
        assert productie.muta(db, departe[2], Stare.PLANIFICAT, Stare.BRIEFAT, componenta="D5").aplicat
    # amânarea însăși: doar planificat, doar mai târziu, doar până la termen
    with sesiune_agentie() as db:
        with pytest.raises(productie.AmanareNepermisa):  # nu mai e planificat
            productie.amana(db, departe[2], dt.datetime.now(dt.UTC) + dt.timedelta(days=1), motiv="test")
        scurt = creeaza(tenant, 2)
        with pytest.raises(productie.AmanareNepermisa):  # ar trece de termen
            productie.amana(db, scurt, dt.datetime.now(dt.UTC) + dt.timedelta(days=1), motiv="test")
        with pytest.raises(ValueError):
            productie.amana(db, scurt, dt.datetime(2030, 1, 1), motiv="fără fus")


def test_a_doua_rulare_in_aceeasi_zi_nu_amana_din_nou_si_rescrie_planul(
    tenant: uuid.UUID, cota_creatie: int, anunturi: AnunturiFalse, admin_engine: Engine
) -> None:
    for zile in range(5, 13):
        creeaza(tenant, zile * 24)  # 8 livrabile = 16 apeluri față de 13
    prima = planificare.planifica(clienti=[tenant])
    assert len(prima.amanate) == 2 and len(anunturi.trimise) == 1
    a_doua = planificare.planifica(clienti=[tenant])
    assert (
        a_doua.amanate == () and a_doua.rezultat.depasiri == () and len(anunturi.trimise) == 1
    )  # nicio alertă nouă
    with admin_engine.connect() as c:
        n = c.execute(
            text("SELECT amanate FROM planificare_planuri WHERE zi = :z"),
            {"z": dt.datetime.now(dt.UTC).date()},
        ).scalar_one()
    assert n == 0  # planul zilei reflectă ultima rulare; amânările rămân pe livrabile


def test_planul_peste_capacitate_din_cauza_celor_protejate_se_spune_in_alerta(
    tenant: uuid.UUID, cota_creatie: int, anunturi: AnunturiFalse
) -> None:
    protejate = [creeaza(tenant, 12) for _ in range(8)]  # 16 apeluri, toate cu termen în 12 ore, față de 13
    plan = planificare.planifica(clienti=[tenant])
    assert plan.amanate == () and set(plan.protejate) == set(protejate) and plan.peste_capacitate
    assert anunturi.titluri() == ["Capacitate: planul depășește cotele"]
    assert (
        "8 cu termen apropiat rămân neatinse" in anunturi.trimise[0][2]
        and "apeluri creatie" in anunturi.trimise[0][2]
    )


def test_fara_cota_pe_profil_nu_incape_nimic_nepotejat(
    tenant: uuid.UUID, cost_proba: None, cheie_proba: str, admin_engine: Engine, anunturi: AnunturiFalse
) -> None:
    """Profilul fără niciun model utilizabil are capacitate 0: tot ce nu e protejat se amână (platforma nu pierde munca)."""
    with admin_engine.connect() as c:
        original = c.execute(text("SELECT lant FROM gateway_profiluri WHERE nume = 'creatie'")).scalar_one()
    with admin_engine.begin() as c:
        c.execute(text("UPDATE gateway_profiluri SET lant = '{nu/exista}' WHERE nume = 'creatie'"))
    try:
        departe = creeaza(tenant, 24 * 8)
        apropiat = creeaza(tenant, 20)
        plan = planificare.planifica(clienti=[tenant])
    finally:
        with admin_engine.begin() as c:
            c.execute(
                text("UPDATE gateway_profiluri SET lant = :l WHERE nume = 'creatie'"), {"l": list(original)}
            )
    assert plan.amanate == (departe,) and plan.protejate == (apropiat,)


def test_jobul_zilnic_si_cel_la_cerere_ruleaza_prin_motor(
    cota_creatie: int, porneste_executor: object, anunturi: AnunturiFalse, admin_engine: Engine
) -> None:
    from app import worker

    assert "app.planificare.fluxuri" in worker.MODULE_FLUXURI
    assert callable(planificare.planifica_la_cerere)
    porneste_executor()  # type: ignore[operator]
    job = planificare.planifica_la_cerere()
    assert motor.asteapta_flux(job, timeout_sec=30).stare is motor.StareJob.TERMINAT
    with admin_engine.connect() as c:
        n = c.execute(
            text("SELECT count(*) FROM planificare_planuri WHERE zi = :z"),
            {"z": dt.datetime.now(dt.UTC).date()},
        ).scalar_one()
    assert n == 1
    assert motor.stare_flux(job).coada == Coada.IO.value  # type: ignore[union-attr]
    assert fluxuri.NUME_ZILNIC == "planificare.capacitate_zilnica"
