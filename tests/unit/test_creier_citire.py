"""F4.7 — citirea pentru context a profilului și constrângerilor: nu poate fi o a doua cale spre fapte și oferte."""

import datetime as dt
from typing import Any, cast

import pytest

from app.creier import citire
from app.creier.compartimente import Compartiment
from app.creier.versiuni import RegulaCreier
from app.ids import new_id

LA = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
DB = cast(Any, None)  # nu se atinge: cererile de mai jos sunt refuzate înainte de orice interogare


@pytest.mark.parametrize("comp", [Compartiment.REGISTRU_FAPTE, Compartiment.CATALOG_OFERTE])
def test_faptele_si_ofertele_nu_se_citesc_pe_calea_generica(comp: Compartiment) -> None:
    with pytest.raises(RegulaCreier, match="pentru_context"):
        citire.pentru_context(DB, new_id(), comp, LA)


def test_nivelul_platformei_se_citeste_doar_pentru_constrangeri_si_data_are_fus_orar() -> None:
    with pytest.raises(RegulaCreier, match="constrângeri"):
        citire.pentru_context(DB, new_id(), Compartiment.PROFIL_BRAND, LA, cu_platforma=True)
    with pytest.raises(RegulaCreier, match="fus orar"):
        citire.pentru_context(DB, new_id(), Compartiment.PROFIL_BRAND, dt.datetime(2026, 1, 1))


def test_textul_intrarii_este_determinist_si_cu_etichete_doar_cand_sunt_mai_multe_campuri() -> None:
    assert (
        citire.text_intrare({"regula": "Nu promite livrare în aceeași zi"})
        == "Nu promite livrare în aceeași zi"
    )
    c = {
        "ton": "cald și direct",
        "pozitionare": "Prăjitorie de specialitate",
        "gol": "",
        "nul": None,
        "evitate": ["ieftin", "super"],
    }
    assert citire.text_intrare(c) == (
        "evitate: ieftin, super; pozitionare: Prăjitorie de specialitate; ton: cald și direct"
    )
