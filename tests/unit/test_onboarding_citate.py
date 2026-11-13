"""F4.9 — nucleul pur al vocii clientului: ce respinge verificatorul de citate (fără model, fără bază)."""

import pytest

from app.onboarding.citate import CitatExtras, cheie_citat, motiv_respingere

PASAJ = (
    "Cafeaua Etiopia Guji miroase a flori și are gust de afine. — Ioana M.\n\n"
    "Scrieți-mi la ana.test@exemplu.test dacă aveți nelămuriri despre abonament.\n\n"
    "Pot comanda cafea măcinată? Nu am râșniță acasă și nu vreau să cumpăr una.\n\n"
    "Ioana M.: livrarea a fost rapidă și pachetul bine închis, recomand."
)


def citat(text: str) -> CitatExtras:
    return CitatExtras(text=text, tip="recenzie", tema="cafea", sentiment="pozitiv")


@pytest.mark.parametrize(
    ("text", "motiv"),
    [
        ("Cafeaua Etiopia Guji miroase a flori și are gust de afine.", None),
        ("Pot comanda cafea măcinată? Nu am râșniță acasă și nu vreau să cumpăr una.", None),
        ("Cafeaua Etiopia Guji miroase a flori și are gust de afine. — Ioana M.", "nume_autor"),  # semnătură
        ("Ioana M.: livrarea a fost rapidă și pachetul bine închis, recomand.", "nume_autor"),  # atribuire
        ("Scrieți-mi la ana.test@exemplu.test dacă aveți nelămuriri despre abonament.", "date_personale"),
        ("Cafeaua este cea mai bună din lume și nu am găsit alta mai bună.", "citat_negasit"),  # inventat
        ("Gust de afine.", "lungime"),  # prea scurt
        ("Cafeaua Etiopia Guji miroase a flori și are gust de afine." + " x" * 200, "lungime"),
    ],
)
def test_motivele_de_respingere_ale_unui_citat(text: str, motiv: str | None) -> None:
    assert motiv_respingere(citat(text), PASAJ) == motiv


def test_cheia_citatului_nu_depinde_de_spatii_sau_majuscule() -> None:
    assert cheie_citat("Cafea  bună, proaspătă") == cheie_citat("cafea bună, proaspătă")
    assert cheie_citat("o cafea") != cheie_citat("altă cafea")
