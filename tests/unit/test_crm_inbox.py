"""F12.7 — clasificarea mesajelor de test (reguli, fără bază de date)."""

import pytest

from app.crm.inbox import CLASE, clasifica

MESAJE_DE_TEST = [
    ("Bună! Ce program aveți sâmbăta?", "intrebare"),
    ("Lucrați și cu firme din Cluj?", "intrebare"),
    ("Cât costă pachetul pentru o cafenea?", "cerere_pret"),
    ("Vreau o ofertă pentru un magazin online", "cerere_pret"),
    ("Mulțumesc mult, super articolul!", "lauda"),
    ("Bravo, felicitări echipei 👏", "lauda"),
    ("Sunt foarte dezamăgit, nu mi-a răspuns nimeni de o săptămână", "critica"),
    ("Groaznic serviciu. Nu recomand!", "critica"),
    ("Au trecut două săptămâni și postările întârzie. De ce?", "critica"),
    ("Am o întrebare despre tratamentul meu, ce medic recomandați?", "sensibil"),
    ("Vreau să vorbesc cu avocatul vostru despre contract", "sensibil"),
    ("Cum îmi primesc banii înapoi?", "sensibil"),
    ("Ai câștigat un premiu! Click aici: https://castig.example/x", "spam"),
    ("Investiți în bitcoin cu noi, profit zilnic", "spam"),
    ("Sunteți niște idioți", "spam"),
    ("hmm", "neclar"),
    ("", "neclar"),
]


@pytest.mark.parametrize(("text", "clasa"), MESAJE_DE_TEST)
def test_mesajele_de_test_sunt_clasificate_corect(text: str, clasa: str) -> None:
    assert clasifica(text)[0] == clasa


def test_toate_clasele_din_17_8_sunt_acoperite() -> None:
    assert {c for _, c in MESAJE_DE_TEST} == set(CLASE)
