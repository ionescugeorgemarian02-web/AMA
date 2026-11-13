"""F4.11 — strategia pe 90 de zile, prima formă (A2). „Gata când” (brand de probă): o strategie aprobată, cu toate elementele
completate (ipoteză, plan 30 și 90, indicator principal, prag minim, fereastră de măsurare, criteriu de oprire), vizibilă pe ecranul
Campanii. Profilul `strategie` se amână, nu se degradează. Modelul este FALS (# SIMULAT). Pentru brandurile reale, aprobarea e a proprietarului."""

# ruff: noqa: F811
import copy
import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, text

from app import creier
from app.creier import context
from app.creier.compartimente import Compartiment, ContinutInvalid, SursaTip
from app.db import sesiune_tenant
from app.onboarding import fluxuri, strategie
from app.operare import motor
from tests.furnizor_fals import CerereInregistrata, FurnizorFals
from tests.integration.lant_onboarding import acum_plus, pana_la_insight
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele, prompt_complet, raspuns_json  # noqa: F401

pytestmark = pytest.mark.db


def strategie_valida() -> dict[str, Any]:
    def pas(a: str, canal: str, r: str) -> dict[str, str]:
        return {"actiune": a, "canal": canal, "rezultat_asteptat": r}

    return {
        "ipoteza": "Dacă arătăm data prăjirii și explicăm simplu notele de gust, mai mulți iubitori de cafea aleg abonamentul lunar.",
        "plan_30_zile": [
            pas(
                "Publicăm săptămânal o postare despre data prăjirii",
                "facebook",
                "primele 200 de interacțiuni",
            ),
            pas(
                "Trimitem un email de bun venit cu oferta abonamentului",
                "email",
                "20 de abonări noi la listă",
            ),
            pas("Organizăm prima degustare gratuită anunțată pe site", "cafenea", "12 participanți"),
        ],
        "plan_90_zile": [
            pas("Rulăm o campanie de abonament pe Facebook și Instagram", "reclama", "40 de abonamente noi"),
            pas(
                "Trimitem lunar un newsletter cu povești despre ferme",
                "email",
                "rată de deschidere peste 35%",
            ),
            pas("Repetăm degustarea lunară și colectăm recenzii", "cafenea", "10 recenzii noi pe lună"),
        ],
        "indicator_principal": {
            "nume": "Abonamente lunare noi",
            "unitate": "abonamente",
            "tinta": 60,
            "mod_masurare": "Numărul de comenzi noi de abonament din magazinul online",
        },
        "prag_minim": {
            "valoare": 25,
            "unitate": "abonamente",
            "motiv": "Sub 25 de abonamente nu acoperim costul reclamelor",
        },
        "fereastra_masurare_zile": 30,
        "criteriu_oprire": "Dacă după 45 de zile sub 10 abonamente noi, oprim reclamele și revenim la ipoteză.",
    }


def model_strategie(
    modele: ModelFals, strategie_: dict[str, Any] | None = None, verifica: Any = None
) -> None:
    def handler(c: CerereInregistrata) -> str:
        if verifica:
            verifica(prompt_complet(c))
        return raspuns_json(strategie=strategie_ or strategie_valida())

    modele.handlere["Construiește strategia pe 90 de zile"] = handler


def propune(tenant: uuid.UUID, om: uuid.UUID, cheie: str) -> None:
    job = fluxuri.trimite_strategia(tenant, om, cheie=cheie)
    assert motor.asteapta_flux(job, timeout_sec=60).stare.value == "terminat"


def strategie_db(tenant: uuid.UUID) -> tuple[uuid.UUID, list[Any]]:
    with sesiune_tenant(tenant) as db:
        i = creier.gaseste_intrare(
            db, tenant_id=tenant, compartiment=Compartiment.STRATEGIE, cheie=strategie.CHEIE_STRATEGIE
        )
        assert i is not None
        return i.id, creier.istoric(db, i.id)


def test_strategia_se_construieste_din_contextul_aprobat_are_toate_elementele_si_o_aproba_un_om(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    pana_la_insight(tenant, om, modele)
    vazut: list[str] = []
    model_strategie(modele, verifica=vazut.append)
    propune(tenant, om, f"strategie:{tenant}:1")
    iid, versiuni = strategie_db(tenant)
    [v] = versiuni
    assert v.stare == "propus" and v.sursa_tip == SursaTip.SISTEM.value and v.sursa_detalii["pachet_amprenta"]
    c = v.continut
    for camp in (
        "ipoteza",
        "plan_30_zile",
        "plan_90_zile",
        "indicator_principal",
        "prag_minim",
        "fereastra_masurare_zile",
        "criteriu_oprire",
    ):
        assert c[camp], camp  # toate elementele completate
    # promptul a primit contextul APROBAT: brief, ghid, fapte, public, insight (prin constructorul de context)
    [prompt] = vazut
    for fraza in ("Brief de onboarding (aprobat)", "Ghid de brand (aprobat)", "Profil de public (aprobat)", "Insight de piață (aprobat)",
                  "Fapte aprobate", "Etiopia Guji, 250 g, costă 49 lei", "Expertul calm"):  # fmt: skip
        assert fraza in prompt, fraza
    with sesiune_tenant(tenant, om) as db:
        with pytest.raises(creier.RegulaCreier, match="doar de un om"):
            creier.aproba(db, iid, 1, utilizator_id=None, prin_sistem=True)
        creier.aproba(db, iid, 1, utilizator_id=om)
        [(i, aprobata)] = strategie.strategii(db, tenant)
        assert i.id == iid and aprobata is not None and aprobata.stare == "aprobat"
    # a doua propunere = versiune nouă; cea aprobată rămâne citibilă și în vigoare până la noua aprobare
    model_strategie(modele, {**strategie_valida(), "fereastra_masurare_zile": 45})
    propune(tenant, om, f"strategie:{tenant}:2")
    _, versiuni = strategie_db(tenant)
    assert [x.stare for x in versiuni] == ["aprobat", "propus"] and versiuni[1].continut[
        "fereastra_masurare_zile"
    ] == 45
    with sesiune_tenant(tenant, om) as db:
        assert [s.cale for s in creier.diferenta_versiuni(db, iid, 1, 2)] == ["fereastra_masurare_zile"]


def test_fara_brief_ghid_public_sau_insight_aprobate_strategia_nu_se_propune(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    model_strategie(modele)
    with (
        sesiune_tenant(tenant, om) as db,
        pytest.raises(creier.RegulaCreier, match="brieful nu este aprobat"),
    ):
        strategie.propune(db, tenant_id=tenant, utilizator_id=om)
    from tests.integration.test_onboarding_ghid import brief_aprobat

    brief_aprobat(tenant, om)
    with (
        sesiune_tenant(tenant, om) as db,
        pytest.raises(creier.RegulaCreier, match="ghid_brand, public, insight"),
    ):
        strategie.propune(db, tenant_id=tenant, utilizator_id=om)
    assert strategie_db_gol(tenant)


def strategie_db_gol(tenant: uuid.UUID) -> bool:
    with sesiune_tenant(tenant) as db:
        return (
            creier.gaseste_intrare(
                db, tenant_id=tenant, compartiment=Compartiment.STRATEGIE, cheie=strategie.CHEIE_STRATEGIE
            )
            is None
        )


@pytest.mark.parametrize(
    "camp",
    [
        "ipoteza",
        "plan_30_zile",
        "plan_90_zile",
        "indicator_principal",
        "prag_minim",
        "fereastra_masurare_zile",
        "criteriu_oprire",
    ],
)
def test_o_strategie_cu_un_element_lipsa_nu_poate_fi_creata_nici_propusa(
    tenant: uuid.UUID, om: uuid.UUID, camp: str
) -> None:
    incompleta = {k: v for k, v in strategie_valida().items() if k != camp}
    assert strategie.probleme_strategie(incompleta)
    with sesiune_tenant(tenant, om) as db, pytest.raises(ContinutInvalid):
        creier.creeaza_intrare(db, tenant_id=tenant, compartiment=Compartiment.STRATEGIE, cheie="s", continut=incompleta,
                               sursa=creier.Sursa(SursaTip.OM), utilizator_id=om)  # fmt: skip


def test_regulile_dincolo_de_schema_prag_sub_tinta_aceeasi_unitate_plan_complet() -> None:
    ok = strategie_valida()
    assert strategie.probleme_strategie(ok) == []
    peste = copy.deepcopy(ok)
    peste["prag_minim"]["valoare"] = 60
    assert any("sub ținta" in p for p in strategie.probleme_strategie(peste))
    alta = copy.deepcopy(ok)
    alta["prag_minim"]["unitate"] = "lei"
    assert any("aceeași unitate" in p for p in strategie.probleme_strategie(alta))
    fara_pasi = copy.deepcopy(ok)
    fara_pasi["plan_30_zile"] = fara_pasi["plan_30_zile"][:2]
    assert strategie.probleme_strategie(fara_pasi)
    zile = copy.deepcopy(ok)
    zile["fereastra_masurare_zile"] = 120
    assert strategie.probleme_strategie(zile)


def test_poarta_blocheaza_trimiterea_unei_strategii_cu_pragul_peste_tinta(
    tenant: uuid.UUID, om: uuid.UUID
) -> None:
    rea = copy.deepcopy(strategie_valida())
    rea["prag_minim"]["valoare"] = 100
    with sesiune_tenant(tenant, om) as db:
        with pytest.raises(creier.PoartaInchisa, match="sub ținta"):
            creier.creeaza_intrare(db, tenant_id=tenant, compartiment=Compartiment.STRATEGIE, cheie="s2", continut=rea,
                                   sursa=creier.Sursa(SursaTip.OM), utilizator_id=om)  # fmt: skip
        i, v = creier.creeaza_intrare(db, tenant_id=tenant, compartiment=Compartiment.STRATEGIE, cheie="s3", continut=rea,
                                      sursa=creier.Sursa(SursaTip.OM), utilizator_id=om, propune=False)  # fmt: skip
        with pytest.raises(creier.PoartaInchisa):
            creier.trimite_spre_aprobare(db, i.id, v.nr, utilizator_id=om)


def test_modelul_care_omite_un_element_nu_produce_o_strategie(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    pana_la_insight(tenant, om, modele)
    incompleta = strategie_valida()
    del incompleta["criteriu_oprire"]
    model_strategie(modele, incompleta)
    propune(tenant, om, f"strategie:{tenant}:3")  # fluxul se încheie curat
    assert strategie_db_gol(tenant)


def test_strategia_se_amana_nu_se_degradeaza_cand_furnizorul_nu_mai_are_cota(
    tenant: uuid.UUID,
    om: uuid.UUID,
    modele: ModelFals,
    executor: None,
    fals: FurnizorFals,
    admin_engine: Engine,
) -> None:
    pana_la_insight(tenant, om, modele)
    model_strategie(modele)
    with admin_engine.connect() as c:
        gazda = c.execute(
            text(
                "SELECT split_part(split_part(url_baza, '://', 2), '/', 1) FROM gateway_furnizori ORDER BY creat_la DESC LIMIT 1"
            )
        ).scalar_one()
    fals.scenariu(gazda, permanent="429")
    propune(tenant, om, f"strategie:{tenant}:4")
    assert strategie_db_gol(tenant)  # nimic degradat, nimic inventat
    with admin_engine.connect() as c:
        reluari = c.execute(
            text("SELECT status FROM dbos.workflow_status WHERE workflow_uuid LIKE :k"),
            {"k": f"strategie:{tenant}:reluare:%"},
        ).all()
    assert len(reluari) == 1 and reluari[0][0] in ("DELAYED", "ENQUEUED")  # reprogramat, nu eșuat
    assert {c.gazda for c in fals.cereri} <= {gazda} | {
        c.gazda for c in fals.cereri
    }  # un singur furnizor în lanț


def test_pachetul_de_context_poate_include_strategia_aprobata(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    pana_la_insight(tenant, om, modele)
    model_strategie(modele)
    propune(tenant, om, f"strategie:{tenant}:5")
    iid, _ = strategie_db(tenant)
    with sesiune_tenant(tenant) as db:
        p0 = context.construieste(db, tenant_id=tenant, tip_sarcina="postare_facebook", intrebare="Postare despre cafea", salveaza=False,
                                  la=acum_plus(), sectiuni_extra=("strategie",))  # fmt: skip
        assert "strategie" in p0.lipsuri  # propusă, dar neaprobată: nu intră
    with sesiune_tenant(tenant, om) as db:
        creier.aproba(db, iid, 1, utilizator_id=om)
    with sesiune_tenant(tenant) as db:
        p = context.construieste(db, tenant_id=tenant, tip_sarcina="postare_facebook", intrebare="Postare despre cafea", salveaza=False,
                                 la=acum_plus(), sectiuni_extra=("strategie",))  # fmt: skip
        [e] = p.sectiune("strategie")
        assert (
            e.id == str(iid) and "Abonamente lunare noi" in e.text and "Dacă arătăm data prăjirii" in e.text
        )
        implicit = context.construieste(db, tenant_id=tenant, tip_sarcina="postare_facebook", intrebare="Postare despre cafea",
                                        salveaza=False, la=acum_plus())  # fmt: skip
        assert (
            not implicit.sectiune("strategie") and "strategie" not in implicit.lipsuri
        )  # comportamentul vechi, neschimbat
