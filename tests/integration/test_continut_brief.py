"""F6.2 — autorul de brief (D5). „Gata când”: fiecare intrare de calendar are brief cu fapte permise. Brandul FICTIV
„Cafeneaua Zorilor”, model FALS (# SIMULAT)."""

# ruff: noqa: F811
import uuid

import pytest

from app import continut, creier, productie
from app.continut import brief
from app.db import sesiune_tenant
from tests.continut_utile import model_brief
from tests.integration.lant_continut import calendar_aprobat, cu_briefuri
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele, prompt_complet  # noqa: F401

pytestmark = pytest.mark.db


def test_fiecare_intrare_de_calendar_are_brief_cu_fapte_permise_din_pachet(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    cal, livrabile = cu_briefuri(tenant, om, modele)
    with sesiune_tenant(tenant) as db:
        sloturi = continut.calendar.intrari(db, cal)
        assert len(sloturi) == len(livrabile) == 21
        for s in sloturi:
            assert s.livrabil_id is not None
            b = brief.al_livrabilului(db, s.livrabil_id)
            assert b is not None, s.subiect
            c = b.continut
            assert c["fapte_permise"], s.subiect  # cel puțin un fapt permis, cu id și versiune din Creier
            for f in c["fapte_permise"]:
                assert f["id"] and f["versiune"] and f["text"]
            assert c["canal"] == s.canal and c["tip"] == s.tip and c["subiect"] == s.subiect
            assert c["mesaj_unic"] and c["apel_la_actiune"] and c["format"] and c["scop"] and c["public"]
            assert b.pachet_id is not None
            lv = productie.citeste(db, s.livrabil_id)
            assert lv is not None and lv.stare == "briefat"
            assert "Fapte permise" in brief.text_pentru_autor(c)


def test_un_fapt_inventat_respinge_brieful_si_livrabilul_ramane_planificat(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    _, livrabile = calendar_aprobat(tenant, om, modele)
    vazut: list[str] = []
    model_brief(modele, inventeaza=True)
    h = modele.handlere["Scrie brieful livrabilului"]
    modele.handlere["Scrie brieful livrabilului"] = lambda c: (vazut.append(prompt_complet(c)), h(c))[1]
    with sesiune_tenant(tenant) as db, pytest.raises(brief.BriefInvalid, match="F99 nu este în pachetul"):
        brief.scrie(db, livrabile[0])
    assert "Etiopia Guji" in vazut[0] and "Strategie aprobată (90 de zile)" in vazut[0]
    with sesiune_tenant(tenant) as db:
        assert brief.al_livrabilului(db, livrabile[0]) is None
        lv = productie.citeste(db, livrabile[0])
        assert lv is not None and lv.stare == "planificat"
    # brieful corect e idempotent: a doua cerere întoarce același rând
    model_brief(modele)
    with sesiune_tenant(tenant) as db:
        a = brief.scrie(db, livrabile[0])
        assert brief.scrie(db, livrabile[0]).id == a.id
        with pytest.raises(creier.RegulaCreier, match="nu vine dintr-un calendar"):
            lid = productie.creeaza(db, tenant_id=tenant, tip="postare", canal="facebook").id
            brief.scrie(db, lid)


def test_nucleul_lumii_inchise() -> None:
    b = brief.ContinutBrief(
        scop="Să vindem cafea proaspătă", public="Iubitori de cafea", mesaj_unic="Cafeaua ajunge proaspătă",
        fapte_permise=[], format="Postare scurtă", apel_la_actiune="Comandă acum",
    )  # fmt: skip
    assert brief.probleme_brief(b, {}) == []
    assert brief.probleme_brief(b, {"F1": {}}) == ["brieful trebuie să permită cel puțin un fapt din pachet"]
    b2 = b.model_copy(update={"fapte_permise": ["F1", "F1"]})
    assert brief.probleme_brief(b2, {"F1": {}}) == ["un fapt apare de două ori"]
