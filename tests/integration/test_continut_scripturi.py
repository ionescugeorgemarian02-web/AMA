"""F6.4 — scripturile video scurte (E2). „Gata când”: cinci scripturi trec validarea și se încadrează în durata-țintă. Cascada
REALĂ (validatorii deterministe), brandul FICTIV, modelul FALS (# SIMULAT)."""

# ruff: noqa: F811
import uuid

import pytest

from app import continut, productie, validare
from app.continut import pipeline, scripturi
from app.db import sesiune_tenant
from app.productie import Stare
from tests.continut_utile import model_scripturi
from tests.integration.lant_continut import cu_briefuri, fara_cereri_ramase  # noqa: F401
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fara_cereri_ramase")]


def scripturile(tenant: uuid.UUID, cal: uuid.UUID) -> list[uuid.UUID]:
    with sesiune_tenant(tenant) as db:
        return [
            i.livrabil_id
            for i in continut.calendar.intrari(db, cal)
            if i.tip == "script_video_scurt" and i.livrabil_id
        ]


def test_cinci_scripturi_trec_validarea_si_se_incadreaza_in_durata_tinta(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    cal, _ = cu_briefuri(tenant, om, modele)
    e2 = model_scripturi(modele, prea_lungi={2})  # al doilea script iese prea lung o dată: E2 îl scurtează
    lids = scripturile(tenant, cal)
    assert len(lids) == 4  # o dată pe săptămână în calendar; al cincilea vine din ideea unui slot nou
    with sesiune_tenant(tenant, om) as db:
        extra = productie.creeaza(db, tenant_id=tenant, tip="script_video_scurt", canal="facebook").id
        # același brief ca primul script, ca să treacă prin D5 → E2 la fel ca sloturile (livrabil în afara calendarului
        # nu are brief; aici îl copiem explicit pentru probă)
        b = continut.brief.al_livrabilului(db, lids[0])
        assert b is not None
        db.add(
            continut.Brief(tenant_id=tenant, livrabil_id=extra, pachet_id=b.pachet_id, continut=b.continut)
        )
        productie.muta(db, extra, Stare.PLANIFICAT, Stare.BRIEFAT, componenta="test")
    cinci = [*lids, extra]
    for lid in cinci:
        assert pipeline.produ(tenant, lid) == Stare.ASTEAPTA_APROBARE.value
    with sesiune_tenant(tenant) as db:
        for lid in cinci:
            c = validare.continut.citeste(db, lid)
            assert c.autor == "E2" and 3 <= len(c.campuri["batai"]) <= 6 and c.campuri["cta"]
            assert all(b["voce"] and b["vizual"] and "text_ecran" in b for b in c.campuri["batai"])
            tinta, est = c.campuri["durata_tinta_sec"], c.campuri["durata_estimata_sec"]
            assert tinta == 30 and scripturi.se_incadreaza(est, tinta), est
            # durata e recalculată din text, nu luată de la model
            voci = [b["voce"] for b in c.campuri["batai"]]
            assert est == scripturi.durata_estimata(c.campuri["hook"], voci, c.campuri["cta"])
            assert len(c.campuri["hook"].split()) <= 7  # hook-ul încape în primele 3 secunde
            ultima = validare.ultima_rulare(db, lid)
            assert ultima is not None and ultima.decizie == "trece"
    assert len(e2.cereri) == 6 and "Scurtează vocea" in e2.cereri[2]


def test_un_script_care_nu_se_incadreaza_merge_in_coada_de_erori(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    cal, _ = cu_briefuri(tenant, om, modele)
    model_scripturi(modele, mereu_lung=True)
    lid = scripturile(tenant, cal)[0]
    assert pipeline.produ(tenant, lid) == Stare.COADA_DE_ERORI.value
    with sesiune_tenant(tenant) as db:
        [*_, t] = productie.istoric(db, lid)
        assert "față de ținta de 30 s" in t.motiv


def test_nucleul_duratei() -> None:
    assert (
        scripturi.durata_estimata("Ce gust are cafeaua?", ["unu doi trei patru cinci"] * 3, "Comandă acum.")
        == 9.9
    )  # 21 de cuvinte / 2,5 + 3 × 0,5
    assert scripturi.se_incadreaza(33.0, 30) and not scripturi.se_incadreaza(36.0, 30)
    assert scripturi.durata_tinta({}) == 30 and scripturi.durata_tinta({"durata_tinta_sec": 90}) == 60
