"""F6.5 — adaptorul pe platformă (E10). „Gata când”: aceeași idee are variante corecte ca lungime pentru fiecare canal.
Cascada REALĂ (deterministă), brandul FICTIV, modelul FALS (# SIMULAT)."""

# ruff: noqa: F811
import uuid

import pytest

from app import continut, productie, validare
from app.continut import adaptor, pipeline
from app.db import sesiune_tenant
from app.productie import Stare
from tests.continut_utile import model_adaptor, model_postari
from tests.integration.lant_continut import cu_briefuri, fara_cereri_ramase  # noqa: F401
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fara_cereri_ramase")]


def test_aceeasi_idee_are_variante_corecte_ca_lungime_pe_fiecare_canal(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    cal, _ = cu_briefuri(tenant, om, modele)
    model_postari(modele)
    e10 = model_adaptor(modele)
    with sesiune_tenant(tenant) as db:
        sursa = next(i.livrabil_id for i in continut.calendar.intrari(db, cal) if i.tip == "postare")
    assert sursa is not None and pipeline.produ(tenant, sursa) == Stare.ASTEAPTA_APROBARE.value
    with sesiune_tenant(tenant) as db:
        rez = adaptor.adapteaza(db, sursa)
    assert set(rez.livrabile) == {"instagram", "linkedin", "tiktok"} and rez.neadaptate == {}
    assert len(e10.cereri) == 2 and "tiktok: textul are" in e10.cereri[1]  # TikTok prea lung → cerut din nou
    for lid in rez.livrabile.values():
        assert pipeline.produ(tenant, lid) == Stare.ASTEAPTA_APROBARE.value
    with sesiune_tenant(tenant) as db:
        b_sursa = continut.brief.al_livrabilului(db, sursa)
        assert b_sursa is not None
        lv_sursa = productie.citeste(db, sursa)
        assert lv_sursa is not None
        for canal, lid in rez.livrabile.items():
            lv = productie.citeste(db, lid)
            assert lv is not None and lv.canal == canal and lv.termen_la == lv_sursa.termen_la
            c = validare.continut.citeste(db, lid)
            assert c.autor == "E10" and adaptor.probleme_lungime(canal, c.text, c.campuri["hashtaguri"]) == []
            assert len(c.text) <= adaptor.TINTE[canal]["text"]
            assert len(c.campuri["hashtaguri"]) <= adaptor.TINTE[canal]["hashtaguri"]
            # aceeași idee: brieful sursei, cu canalul schimbat
            b = continut.brief.al_livrabilului(db, lid)
            assert (
                b is not None
                and b.continut["subiect"] == b_sursa.continut["subiect"]
                and b.continut["canal"] == canal
            )
        assert [a.canal for a in adaptor.ale_sursei(db, sursa)] == ["instagram", "linkedin", "tiktok"]
        # idempotent: a doua cerere nu mai cheamă modelul
        assert adaptor.adapteaza(db, sursa).livrabile == rez.livrabile
    assert len(e10.cereri) == 2


def test_nucleul_lungimilor_si_refuzurile(tenant: uuid.UUID) -> None:
    assert adaptor.probleme_lungime("tiktok", "x" * 301, []) == [
        "textul are 301 de caractere; pe tiktok cel mult 300"
    ]
    assert adaptor.probleme_lungime("linkedin", "Text scurt.", ["a", "b", "c", "d"]) == [
        "4 hashtag-uri; pe linkedin cel mult 3"
    ]
    assert adaptor.probleme_lungime("instagram", "Text scurt.", []) == []
    with sesiune_tenant(tenant) as db:
        lid = productie.creeaza(db, tenant_id=tenant, tip="postare", canal="facebook").id
        with pytest.raises(adaptor.AdaptareRefuzata, match="trecut validarea"):
            adaptor.adapteaza(db, lid)
