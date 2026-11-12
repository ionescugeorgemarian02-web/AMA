"""F2.4 — limitele anti-buclă (7.3), nucleu pur."""

import pytest

from app.productie.limite import (
    Depasire,
    Limite,
    depasire_buget,
    depasire_la_intrare,
    intrerupator_declansat,
    rata_esec,
)
from app.productie.stari import STARI_DE_LUCRU, Stare

L = Limite(runde_reparatie=2, predari=12)


def test_a_treia_runda_de_reparatie_nu_se_face() -> None:
    assert depasire_la_intrare(Stare.IN_REPARATIE, 0, 0, L) is None
    assert depasire_la_intrare(Stare.IN_REPARATIE, 1, 0, L) is None
    assert depasire_la_intrare(Stare.IN_REPARATIE, 2, 0, L) is Depasire.RUNDE_REPARATIE


def test_a_treisprezecea_predare_nu_se_face() -> None:
    assert depasire_la_intrare(Stare.IN_SCRIERE, 0, 11, L) is None
    assert depasire_la_intrare(Stare.IN_SCRIERE, 0, 12, L) is Depasire.PREDARI
    assert depasire_la_intrare(Stare.IN_REPARATIE, 0, 12, L) is Depasire.PREDARI


@pytest.mark.parametrize("stare", [s for s in Stare if s not in STARI_DE_LUCRU])
def test_intrarea_in_stari_fara_munca_nu_e_limitata(stare: Stare) -> None:
    assert depasire_la_intrare(stare, 99, 99, L) is None


def test_reparatia_se_judeca_inaintea_predarilor() -> None:
    assert depasire_la_intrare(Stare.IN_REPARATIE, 2, 12, L) is Depasire.RUNDE_REPARATIE


def test_bugetul_se_depaseste_doar_peste_valoare() -> None:
    assert depasire_buget(40, 100.0, 40, 3600) is None, "exact bugetul e încă în regulă"
    assert depasire_buget(41, 100.0, 40, 3600) is Depasire.BUGET_APELURI
    assert depasire_buget(1, 3600.0, 40, 3600) is None
    assert depasire_buget(1, 3600.1, 40, 3600) is Depasire.BUGET_TIMP


def test_rata_de_esec() -> None:
    assert rata_esec(0, 0) is None
    assert rata_esec(7, 3) == pytest.approx(0.3)


@pytest.mark.parametrize(
    ("succese", "esecuri", "asteptat"),
    [
        (1, 1, False),  # 50%, dar doar 2 rezultate: sub volumul minim
        (0, 9, False),  # 100%, dar 9 < 10
        (7, 3, False),  # exact 30%: pragul se depășește strict
        (6, 4, True),  # 40% din 10
        (69, 31, True),  # 31% din 100
        (70, 30, False),
        (10, 0, False),
        (0, 10, True),
        (0, 0, False),
    ],
)
def test_intrerupatorul_cere_volum_si_prag_depasit(succese: int, esecuri: int, asteptat: bool) -> None:
    assert intrerupator_declansat(succese, esecuri, 0.30, 10) is asteptat


def test_pragurile_sunt_parametri_nu_constante() -> None:
    assert intrerupator_declansat(1, 1, 0.30, 2) is True
    assert intrerupator_declansat(1, 1, 0.60, 2) is False
    assert depasire_la_intrare(Stare.IN_REPARATIE, 2, 0, Limite(runde_reparatie=3)) is None
    assert (
        depasire_la_intrare(Stare.IN_REPARATIE, 0, 0, Limite(runde_reparatie=0)) is Depasire.RUNDE_REPARATIE
    )
