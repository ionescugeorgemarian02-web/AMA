"""F-idee (D-032) — etapa de idee înaintea briefului: propune → critica → alege → brief, cu rescrierea o singură dată
și omul la capăt. Brandul FICTIV „Cafeneaua Zorilor”, model FALS (# SIMULAT)."""

# ruff: noqa: F811
import json
import uuid
from typing import Any

import pytest
from sqlalchemy import select

from app import productie
from app.continut import brief, idei, pipeline
from app.continut.modele import IdeeConcept
from app.db import sesiune_tenant
from app.media import biblioteca, cereri
from tests.continut_utile import model_brief
from tests.furnizor_fals import CerereInregistrata
from tests.integration.lant_continut import calendar_aprobat
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.media_utile import fotografie_procedurala
from tests.onboarding_utile import (  # noqa: F401
    FARA_FILMARI,
    ModelFals,
    aliasuri_fapte,
    concept_zorilor,
    critica_idee_fals,
    idei_fals,
    model_fals,
    modele,
    prompt_complet,
    raspuns_json,
)

pytestmark = pytest.mark.db

IDEI = "Propune concepte creative pentru livrabilul"
CRITICA = "Critică conceptele de mai jos"


def _livrabil(tenant: uuid.UUID, livrabile: list[uuid.UUID], tip: str) -> uuid.UUID:
    with sesiune_tenant(tenant) as db:
        return next(lid for lid in livrabile if (lv := productie.citeste(db, lid)) and lv.tip == tip)


def _randuri(tenant: uuid.UUID, lid: uuid.UUID) -> list[IdeeConcept]:
    with sesiune_tenant(tenant) as db:
        rows = list(db.execute(select(IdeeConcept).where(IdeeConcept.livrabil_id == lid)).scalars())
        db.expunge_all()
        return rows


def test_ideea_aleasa_intra_in_brief_si_in_textul_autorului(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    _, livrabile = calendar_aprobat(tenant, om, modele)
    model_brief(modele)
    vazut: dict[str, list[str]] = {"idei": [], "critica": [], "brief": []}
    for cheie, fraza, h in (("idei", IDEI, idei_fals), ("critica", CRITICA, critica_idee_fals)):
        modele.handlere[fraza] = lambda c, k=cheie, h=h: (vazut[k].append(prompt_complet(c)), h(c))[1]
    hb = modele.handlere["Scrie brieful livrabilului"]
    modele.handlere["Scrie brieful livrabilului"] = lambda c: (
        vazut["brief"].append(prompt_complet(c)),
        hb(c),
    )[1]
    lid = _livrabil(tenant, livrabile, "script_video_scurt")

    assert pipeline.idee_si_brief(tenant, lid) is None
    assert "Fapte aprobate" in vazut["idei"][0] and "[F1]" in vazut["idei"][0]
    assert vazut["critica"][0].count("Concept ") >= 5
    for k in ("idei", "critica"):  # inventarul: fără material propriu, plus stock-ul generic
        assert "0 fotografii și 0 filmări" in vazut[k][0] and FARA_FILMARI in vazut[k][0], k
    rows = _randuri(tenant, lid)
    assert sorted((r.sursa, r.nr) for r in rows) == [
        ("imbunatatit", 1),
        *(("propus", n) for n in range(1, 6)),
    ]
    ales = [r for r in rows if r.ales]
    assert len(ales) == 1 and ales[0].sursa == "imbunatatit" and ales[0].scor == 27
    assert all(r.autoevaluare and r.model_critic == r.model_autor for r in rows)  # un singur model în lanț
    assert all(r.note and set(r.note) == set(idei.CRITERII) for r in rows)
    assert ales[0].concept["dovada_text"]  # dovada rezolvată la textul faptului aprobat
    assert ales[0].concept["de_filmat"] == [] and ales[0].concept["material_propriu"] == []
    with sesiune_tenant(tenant) as db:
        assert cereri.deschise(db, tenant, lid) == []  # realizabil din stock: nimic de filmat

    assert "Sâmbătă dimineața, în bucătăria de acasă" in vazut["brief"][0]  # brieful vede conceptul
    with sesiune_tenant(tenant) as db:
        b = brief.al_livrabilului(db, lid)
        assert b is not None and b.continut["idee"]["id"] == str(ales[0].id)
        text = brief.text_pentru_autor(b.continut)
        assert "Conceptul ales" in text and "mâna clientului: deschide pachetul" in text
        assert text.index("Conceptul ales") < text.index("Fapte permise")
        assert productie.citeste(db, lid).stare == "briefat"  # type: ignore[union-attr]
    # idempotent: o a doua trecere nu mai cheamă modelul
    n = len(vazut["idei"])
    with sesiune_tenant(tenant) as db:
        assert idei.pregateste(db, lid)["id"] == str(ales[0].id)
    assert len(vazut["idei"]) == n


def _static(c: CerereInregistrata) -> str:
    """Autorul propune cadre statice; la rescriere (un singur concept cerut) le face în acțiune."""
    p = prompt_complet(c)
    if "Întoarce `concepte`: 1 " in p:
        return idei_fals(c)
    cadre = concept_zorilor()["cadre"]
    cadre[2] = {**cadre[2], "actiune": "stă pe tejghea lângă râșniță"}
    dovada = next(iter(aliasuri_fapte(p)), "")
    return raspuns_json(
        concepte=[concept_zorilor(dovada, cadre=cadre, titlu=f"Static {i}") for i in range(5)]
    )


def test_conceptul_respins_se_rescrie_o_data_cu_obiectiile(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    _, livrabile = calendar_aprobat(tenant, om, modele)
    model_brief(modele)
    cereri: list[str] = []
    modele.handlere[IDEI] = lambda c: (cereri.append(prompt_complet(c)), _static(c))[1]

    def critica_fara_imbunatatire(c: CerereInregistrata) -> str:
        r: dict[str, Any] = json.loads(critica_idee_fals(c))
        return raspuns_json(evaluari=r["evaluari"], nr_imbunatatit=None, imbunatatit=None)

    modele.handlere[CRITICA] = critica_fara_imbunatatire
    lid = _livrabil(tenant, livrabile, "postare")
    assert pipeline.idee_si_brief(tenant, lid) is None
    assert len(cereri) == 2 and "cadrul 3 e static" in cereri[1] and "Rescrie O SINGURĂ dată" in cereri[1]
    rows = _randuri(tenant, lid)
    ales = next(r for r in rows if r.ales)
    assert ales.runda == 2 and ales.sursa == "rescris" and "rescris cu obiecțiile" in ales.motiv
    assert all(any("static" in p for p in r.probleme) for r in rows if r.runda == 1)


def test_dupa_a_doua_respingere_ideea_merge_la_om(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    _, livrabile = calendar_aprobat(tenant, om, modele)
    model_brief(modele)

    def critica_dura(c: CerereInregistrata) -> str:
        r: dict[str, Any] = json.loads(critica_idee_fals(c))
        for e in r["evaluari"]:
            e["realism"] = 2
        return raspuns_json(evaluari=r["evaluari"], nr_imbunatatit=None, imbunatatit=None)

    modele.handlere[CRITICA] = critica_dura
    lid = _livrabil(tenant, livrabile, "postare")
    assert pipeline.idee_si_brief(tenant, lid) == pipeline.IDEE_LA_OM
    rows = _randuri(tenant, lid)
    assert {r.runda for r in rows} == {1, 2} and not any(r.ales for r in rows)
    assert all("eliminat la realism" in " ".join(r.probleme) for r in rows)
    with sesiune_tenant(tenant) as db:
        assert brief.al_livrabilului(db, lid) is None
    assert pipeline.produ(tenant, lid) == pipeline.IDEE_LA_OM  # fără apeluri noi: așteaptă omul
    # omul alege; lanțul continuă din conceptul lui
    with sesiune_tenant(tenant, om) as db:
        idei.alege_manual(db, rows[0].id, utilizator_id=om)
        with pytest.raises(Exception, match="deja un concept ales"):
            idei.alege_manual(db, rows[1].id, utilizator_id=om)
    assert pipeline.idee_si_brief(tenant, lid) is None
    with sesiune_tenant(tenant) as db:
        b = brief.al_livrabilului(db, lid)
        assert b is not None and b.continut["idee"]["id"] == str(rows[0].id)


def test_fara_concept_realizabil_se_alege_cel_mai_bun_si_se_cere_filmarea(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    """Cazul Spița: autorul cere trei cadre proprii, clientul are doar o fotografie (din portal), fără filmări."""
    _, livrabile = calendar_aprobat(tenant, om, modele)
    model_brief(modele)
    with sesiune_tenant(tenant, om) as db:
        biblioteca.incarca(
            db, tenant, fotografie_procedurala(samanta=7), nume_original="tejghea.jpg", sursa="portal",
            utilizator_id=om, rol_vizual="fotografie", subiect="mâna baristului pe tejghea",
        )  # fmt: skip
    vazut: list[str] = []

    def proprii(c: CerereInregistrata) -> str:
        p = prompt_complet(c)
        vazut.append(p)
        dovada = next(iter(aliasuri_fapte(p)), "")
        cadre = concept_zorilor()["cadre"]
        for i in (0, 1, 2):
            cadre[i] = {**cadre[i], "interogari": []}
        return raspuns_json(
            concepte=[concept_zorilor(dovada, cadre=cadre, material_propriu=[1, 2, 3], titlu=f"Propriu {i}")
                      for i in range(5)]
        )  # fmt: skip

    modele.handlere[IDEI] = proprii
    lid = _livrabil(tenant, livrabile, "script_video_scurt")
    assert pipeline.idee_si_brief(tenant, lid) is None
    assert "1 fotografii și 0 filmări" in vazut[0] and "mâna baristului pe tejghea" in vazut[0]
    assert len(vazut) == 1  # niciun concept realizabil, dar cel mai bun trece: fără rescriere
    rows = _randuri(tenant, lid)
    assert all(any(p.startswith(idei.NEREALIZABIL) for p in r.probleme) for r in rows if r.sursa == "propus")
    ales = next(r for r in rows if r.ales)
    # cadrul 3 (foto, mâna baristului) e acoperit de fotografia din portal; 1 și 2 (video) se filmează
    assert ales.concept["de_filmat"] == [1, 2] and "se cere filmarea cadrelor 1, 2" in ales.motiv
    with sesiune_tenant(tenant) as db:
        c = cereri.deschise(db, tenant, lid)
        assert [(x.versiune, x.scena) for x in c] == [(cereri.VERSIUNE_IDEE, 1), (cereri.VERSIUNE_IDEE, 2)]
        assert (
            c[0].cerere.startswith("Filmează la client o filmare verticală")
            and "mâna clientului" in c[0].cerere
        )
