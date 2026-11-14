"""F7.10 — cercetarea SEO și articolele. „Gata când”: două articole pentru blogul agenției trec validarea și lista
on-page, fiecare cu sursele citate. Pașii cu model (plan, scriere, editare) sunt modelul FALS (# SIMULAT, texte
scriptate); grupurile pe intenție, lista on-page și validarea sunt reale. Sursele sunt inventate (example.org)."""

# ruff: noqa: F811
import json
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from app import seo
from app.db import sesiune_tenant
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele, prompt_complet, raspuns_json  # noqa: F401

pytestmark = pytest.mark.db
CUVINTE = ["cum alegi o agenție de marketing", "cum alegi agenția de marketing potrivită",
           "marketing pentru firme mici", "prețuri agenție de marketing"]  # fmt: skip
SURSE = [
    {"titlu": "Ghid de marketing pentru IMM-uri", "url": "https://example.org/ghid-imm",
     "pasaj": "Firmele mici câștigă clienți când publică regulat și răspund repede la întrebări."},
    {"titlu": "Studiu despre încrederea clienților", "url": "https://example.org/incredere",
     "pasaj": "Clienții au mai multă încredere în firmele care arată clar cine sunt și ce oferă."},
    {"titlu": "Sursă necitată", "url": "https://example.org/altceva", "pasaj": "Un pasaj care nu se folosește."},
]  # fmt: skip
FRAZE = [
    "O firmă mică are nevoie de un mesaj clar, repetat cu răbdare pe canalele unde își caută clienții.",
    "Când publici regulat, oamenii încep să te recunoască și să te aleagă mai ușor [1].",
    "Un răspuns rapid la o întrebare transformă de multe ori un curios într-un client fidel.",
    "Clienții vor să știe cine ești, ce oferi și cum te pot contacta, fără să caute mult [2].",
    "Merită să notezi întrebările frecvente și să le transformi în articole sau postări scurte.",
    "Fiecare material trebuie verificat înainte de publicare, ca să rămână fidel firmei tale.",
    "Un calendar simplu, pe o lună, te ajută să nu publici totul într-o singură săptămână.",
    "Fotografiile reale ale echipei și ale locului spun multe despre felul în care lucrezi.",
]


def articol(principal: str) -> str:
    intro = f"Dacă te întrebi {principal}, începe cu ce vrei să obții în următoarele luni. " + FRAZE[0]
    sectiuni = []
    for i, titlu in enumerate(["Ce urmărești de la început", "Cum verifici o propunere", "Ce întrebi la prima discuție",
                               "Cum măsori dacă merge"]):  # fmt: skip
        paragrafe = [" ".join(FRAZE[(i + k) % len(FRAZE)] for k in range(4)) for _ in range(1)]
        paragrafe.append(" ".join(FRAZE[(i + k + 4) % len(FRAZE)] for k in range(4)))
        sectiuni.append({"titlu": titlu, "paragrafe": paragrafe})
    return raspuns_json(introducere=intro, sectiuni=sectiuni)


def scriptat(modele: ModelFals) -> None:
    def plan(c: object) -> str:
        p = prompt_complet(c)  # type: ignore[arg-type]
        principal = re.search(r"Cuvântul principal: (.+)", p).group(1).strip()  # type: ignore[union-attr]
        titlu = f"Ghid: {principal}".capitalize()[:65]
        descriere = (f"Află {principal}: ce urmărești, ce întrebi și cum verifici rezultatele, pas cu pas, "
                     "pentru o firmă mică.")[:160]  # fmt: skip
        return raspuns_json(titlu=titlu, descriere=descriere, sectiuni=[
            {"titlu": "Ce urmărești", "idee": "Obiectivul primelor luni."},
            {"titlu": "Cum verifici", "idee": "Ce ceri să vezi într-o propunere."},
            {"titlu": "Ce măsori", "idee": "Semnele că merge."}])  # fmt: skip

    def text(c: object) -> str:
        p = prompt_complet(c)  # type: ignore[arg-type]
        return articol(re.search(r"Cuvântul principal[^:]*: (.+)", p).group(1).strip())  # type: ignore[union-attr]

    modele.handlere["Fă planul articolului"] = plan
    modele.handlere["Scrie articolul"] = text
    modele.handlere["Editează articolul"] = text


def test_doua_articole_trec_validarea_si_lista_on_page_cu_surse(
    client: TestClient, tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals
) -> None:
    grupuri = seo.cuvinte.grupeaza(CUVINTE)
    assert [(g.intentie, len(g.cuvinte)) for g in grupuri] == [("informationala", 2), ("informationala", 1),
                                                               ("comerciala", 1)]  # fmt: skip
    scriptat(modele)
    rezultate = []
    with sesiune_tenant(tenant, om) as db:
        for g in grupuri[:2]:
            rezultate.append(seo.articole.scrie(db, tenant, g, SURSE))
    for r in rezultate:
        assert r["on_page"] == [] and r["validare"] is True and r["publicat"] is True, json.dumps(
            r["blocante"], ensure_ascii=False
        )
        assert [s["url"] for s in r["surse_citate"]] == [
            "https://example.org/ghid-imm",
            "https://example.org/incredere",
        ]
        h = client.get(f"/site/blog/{r['slug']}").text
        assert "Surse" in h and "https://example.org/incredere" in h and "example.org/altceva" not in h
    assert rezultate[0]["slug"] != rezultate[1]["slug"]
    blog = client.get("/site/blog").text
    assert all(f'href="/site/blog/{r["slug"]}"' in blog for r in rezultate)


def test_lista_on_page_prinde_problemele() -> None:
    g = seo.cuvinte.grupeaza(["cum alegi o agenție de marketing"])[0]
    b = seo.articole.brief(g, SURSE)
    a = json.loads(articol(g.principal))
    probleme = seo.articole.verifica_on_page("Titlu scurt", "Descriere prea scurtă.", "titlu-scurt",
                                             {**a, "introducere": "Fără cuvânt [7]."}, b)  # fmt: skip
    assert len(probleme) >= 5 and "fiecare citare are o sursă în listă" in probleme
