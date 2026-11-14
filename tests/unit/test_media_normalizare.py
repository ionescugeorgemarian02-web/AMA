"""F8.2 — normalizarea textului românesc. „Gata când”: setul de 100 de fraze de probă este citit corect."""

import tomllib
from pathlib import Path

import pytest

from app.media import normalizare

FRAZE = tomllib.loads((Path(__file__).parents[1] / "fixtures" / "fraze_normalizare.toml").read_text())[
    "fraze"
]
DICTIONAR = {"V60": "vi șaizeci", "Guji": "Gugi", "espresso": "espreso"}


def test_setul_are_100_de_fraze_distincte() -> None:
    assert len(FRAZE) == 100 and len({f for f, _ in FRAZE}) == 100


@pytest.mark.parametrize(("scris", "citit"), FRAZE)
def test_fraza_de_proba_este_citita_corect(scris: str, citit: str) -> None:
    rezultat = normalizare.normalizeaza(scris, DICTIONAR)
    assert rezultat == citit
    assert normalizare.fara_cifre(rezultat) and not set("şţŞŢ%€&#@") & set(rezultat)


@pytest.mark.parametrize(
    ("n", "fem", "cuvinte"),
    [
        (0, False, "zero"), (11, False, "unsprezece"), (12, True, "douăsprezece"), (99, False, "nouăzeci și nouă"),
        (200, False, "două sute"), (1001, False, "o mie unu"), (2026, False, "două mii douăzeci și șase"),
        (20000, False, "douăzeci de mii"), (2_000_000, False, "două milioane"),
    ],
)  # fmt: skip
def test_cardinale(n: int, fem: bool, cuvinte: str) -> None:
    assert normalizare.cardinal(n, fem=fem) == cuvinte
