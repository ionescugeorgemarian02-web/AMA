"""F4.5 — nucleele pure ale ghidului de brand: verificările unei variante și randarea pentru context."""

import copy
from typing import Any

import pytest

from app.onboarding import ghid
from tests.integration.test_onboarding_ghid import varianta


def test_o_varianta_valida_nu_are_probleme_si_se_randeaza_pe_scurt() -> None:
    v = varianta("Barista prietenos", "cald", ["ieftin", "miraculos"])
    assert ghid.probleme_varianta(v) == []
    g = ghid.valideaza_ghid({**v, "origine": "varianta", "din_variante": [1]})
    text = ghid.randeaza(g.model_dump(mode="json")) or ""
    assert (
        text.startswith("Ton „Barista prietenos”") and "Da:" in text and "Nu:" in text and "[email]" in text
    )
    assert ghid.randeaza({"ton": "altceva"}) is None  # alt fel de profil: randarea implicită


def test_exemplele_trebuie_sa_fie_pe_cel_putin_trei_canale() -> None:
    v = varianta("A", "cald", ["ieftin", "miraculos"])
    for e in v["exemple"]:
        e["canal"] = "email"
    assert any("3 canale" in p for p in ghid.probleme_varianta(v))


def test_vocabularul_interzis_nu_apare_in_exemple_nici_fara_diacritice_sau_cu_majuscule() -> None:
    v = varianta("A", "cald", ["revoluționar", "ieftin"])
    v["exemple"][1]["text"] = "Salut! Un gust REVOLUTIONAR pleacă marți din Brașov, proaspăt prăjit."
    probleme = ghid.probleme_varianta(v)
    assert len(probleme) == 1 and "email" in probleme[0]
    v2 = copy.deepcopy(v)
    v2["vocabular_interzis"] = ["REVOLUȚIONAR", "ieftin"]  # alte litere mari / diacritice: același cuvânt
    assert any("folosește vocabular interzis" in p for p in ghid.probleme_varianta(v2))


def test_vocabularul_preferat_si_cel_interzis_nu_se_suprapun() -> None:
    v = varianta("A", "cald", ["proaspăt", "ieftin"])  # „proaspăt” e și în cel preferat
    assert any("se suprapun" in p for p in ghid.probleme_varianta(v))


def test_schema_cere_minimele() -> None:
    v: dict[str, Any] = varianta("A", "cald", ["ieftin", "miraculos"])
    for camp, gol in (("reguli_da", []), ("reguli_nu", ["o regulă"]), ("vocabular_preferat", ["a", "b"]),
                      ("vocabular_interzis", ["a"]), ("exemple", v["exemple"][:2])):  # fmt: skip
        with pytest.raises(ghid.VariantaInvalida):
            ghid.valideaza_ghid({**v, camp: gol})
