"""F12.4 — regula de scor: cele trei grupe și lead-ul mare (fără bază de date)."""

import pytest

from app.crm import CrmRefuzat
from app.crm.calificare import INTREBARI, INTRODUCERE, puncteaza

BUN = {"nisa": "horeca", "buget": "1000_3000", "termen": "imediat", "decident": "da"}


@pytest.mark.parametrize(
    ("schimbare", "grupa", "scor", "la_om"),
    [
        ({}, "suna_azi", 4, False),
        ({"decident": "impreuna", "termen": "1_3_luni"}, "suna_azi", 4, False),
        ({"termen": "peste_3_luni"}, "hraneste", 3, False),
        ({"buget": "nu_stiu"}, "hraneste", 3, False),
        ({"decident": "nu", "termen": "doar_ma_informez"}, "hraneste", 2, False),
        ({"nisa": "alta"}, "nepotrivit", 3, False),
        ({"buget": "sub_1000"}, "nepotrivit", 3, False),
        ({"buget": "peste_10000", "termen": "peste_3_luni"}, "suna_azi", 3, True),
        ({"nisa": "alta", "buget": "peste_10000"}, "nepotrivit", 3, False),
    ],
)
def test_grupele(schimbare: dict[str, str], grupa: str, scor: int, la_om: bool) -> None:
    s = puncteaza({**BUN, **schimbare})
    assert (s.grupa, s.scor, s.la_om) == (grupa, scor, la_om)


def test_motivele_si_validarea() -> None:
    assert "lipsește: termen" in puncteaza({**BUN, "termen": "peste_3_luni"}).motive
    assert puncteaza({**BUN, "nisa": "alta"}).motive == ["nișa nu e una în care lucrăm"]
    with pytest.raises(CrmRefuzat):
        puncteaza({**BUN, "buget": "un milion"})
    with pytest.raises(CrmRefuzat):
        puncteaza({"nisa": "horeca"})


def test_asistentul_se_prezinta_ca_ai_si_pune_intre_3_si_5_intrebari() -> None:
    assert "asistentul AI" in INTRODUCERE and "om" in INTRODUCERE
    assert 3 <= len(INTREBARI) <= 5
