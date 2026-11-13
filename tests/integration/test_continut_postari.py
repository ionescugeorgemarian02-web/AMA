"""F6.3 — hook-uri și postări (E1, E4, E8). „Gata când”: zece postări trec validarea, cel mult două cu reparație. Cascada
REALĂ (validatorii deterministe; judecătorii opriți ca în configurarea implicită), brandul FICTIV, modelul FALS (# SIMULAT)."""

# ruff: noqa: F811
import uuid

import pytest

from app import continut, productie, validare
from app.continut import pipeline, scriere
from app.db import sesiune_tenant
from app.operare import motor
from app.productie import Stare
from tests.continut_utile import model_postari
from tests.integration.lant_continut import cu_briefuri, fara_cereri_ramase  # noqa: F401
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fara_cereri_ramase")]


def postari(tenant: uuid.UUID, cal: uuid.UUID) -> list[uuid.UUID]:
    with sesiune_tenant(tenant) as db:
        return [
            i.livrabil_id for i in continut.calendar.intrari(db, cal) if i.tip == "postare" and i.livrabil_id
        ]


def test_zece_postari_trec_validarea_cel_mult_doua_cu_reparatie(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    cal, _ = cu_briefuri(tenant, om, modele)
    autor = model_postari(modele, stricate={3, 7})  # a treia și a șaptea ies fără diacritice
    zece = postari(tenant, cal)[:10]
    assert len(zece) == 10
    for lid in zece:
        assert pipeline.produ(tenant, lid) == Stare.ASTEAPTA_APROBARE.value  # L1: validată, așteaptă omul
    with sesiune_tenant(tenant) as db:
        cu_reparatie = 0
        for lid in zece:
            lv = productie.citeste(db, lid)
            assert lv is not None
            cu_reparatie += lv.runde_reparatie > 0
            ultima = validare.ultima_rulare(db, lid)
            assert ultima is not None and ultima.versiune == lv.versiune and ultima.decizie == "trece"
            c = validare.continut.citeste(db, lid)
            assert c.autor == "E4" and c.campuri["hook"] and c.campuri["hashtaguri"] == ["cafea", "Brasov"]
            assert c.text.startswith(c.campuri["hook"])
            # E1: patru variante salvate, cu tiparul și scorul lor; aleasă e întrebarea legată de subiect
            v = scriere.variante(db, lid)
            assert len(v) == 4 and [x.nr for x in v if x.ales] == [3]
            assert "cifra_fara_fapt" in v[0].probleme and "G8.hook_deschidere_slaba" in v[1].probleme
            assert productie.aprobari.cerere_activa(db, lid) is not None
        assert cu_reparatie == 2 <= 2
    assert len(autor.reparatii) == 2 and all("[G10]" in r for r in autor.reparatii)


def test_fluxul_durabil_duce_postarea_la_aprobare(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    cal, _ = cu_briefuri(tenant, om, modele)
    model_postari(modele)
    lid = postari(tenant, cal)[0]
    job = continut.fluxuri.trimite_productia(tenant, lid, cheie=f"produ:{lid}")
    assert motor.asteapta_flux(job, timeout_sec=120).stare.value == "terminat"
    assert pipeline.stare(tenant, lid) is Stare.ASTEAPTA_APROBARE
    # a doua trimitere găsește livrabilul unde l-a lăsat și nu mai scrie nimic
    assert pipeline.produ(tenant, lid) == Stare.ASTEAPTA_APROBARE.value
    with sesiune_tenant(tenant) as db:
        assert len(validare.continut.versiuni(db, lid)) == 1


def test_fara_brief_nu_se_scrie_si_un_livrabil_strain_nu_primeste_autorul(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals
) -> None:
    with sesiune_tenant(tenant) as db:
        lid = productie.creeaza(db, tenant_id=tenant, tip="postare", canal="facebook").id
        productie.muta(db, lid, Stare.PLANIFICAT, Stare.BRIEFAT, componenta="test")
        with pytest.raises(scriere.ScriereRefuzata, match="nu are brief"):
            scriere.scrie(db, lid)
        # sursa de autori a producției nu răspunde pentru livrabilele fără brief (F5 rămâne „fără autor”)
        assert validare.autor.curent() is not None
        sarcina = validare.SarcinaReparatie(
            livrabil_id=lid, tenant_id=tenant, tip="postare", canal="facebook", versiune=1, runda=1,
            continut=validare.Continut(versiune=1, text="x"), instructiune="",
        )  # fmt: skip
        assert scriere.repara(db, sarcina) is None
