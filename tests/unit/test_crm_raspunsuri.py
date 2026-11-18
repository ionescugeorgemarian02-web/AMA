"""F12.8 — regulile din 17.8, ferestrele de mesagerie și dezvăluirea AI (pure)."""

import datetime as dt

import pytest

from app.crm.raspunsuri import CALE_OM, PREFIX_AI, decide, in_fereastra

ACUM = dt.datetime(2026, 11, 18, 12, 0, tzinfo=dt.UTC)


@pytest.mark.parametrize(
    ("clasa", "text", "l1", "l2"),
    [
        ("intrebare", "Ce program aveți?", "propune", "raspunde"),
        ("intrebare", "Faceți și logo-uri?", "la_om", "la_om"),  # fără fapt în registru
        ("cerere_pret", "Cât costă?", "propune", "raspunde"),
        ("lauda", "Bravo!", "propune", "raspunde"),
        ("neclar", "hmm", "propune", "raspunde"),
        ("critica", "Groaznic serviciu", "la_om", "la_om"),
        ("sensibil", "Ce tratament luați?", "la_om", "la_om"),
        ("spam", "bitcoin", "ascunde", "ascunde"),
        ("lauda", "om", "la_om", "la_om"),  # persoana cere un om
    ],
)
def test_ce_face_platforma_pe_clasa_si_nivel(clasa: str, text: str, l1: str, l2: str) -> None:
    assert decide(clasa, text, "L1").actiune == l1
    assert decide(clasa, text, "L4" if l2 == "raspunde" else "L2").actiune == l2


def test_textul_sistemului_se_prezinta_ca_ai_si_are_calea_spre_om() -> None:
    for clasa, text in (
        ("intrebare", "Ce program aveți?"),
        ("cerere_pret", "Cât costă?"),
        ("lauda", "Super"),
    ):
        t = decide(clasa, text, "L2").text
        assert t.startswith(PREFIX_AI) and t.endswith(CALE_OM)
    critica = decide("critica", "Dezamăgit", "L4")
    assert critica.text and not critica.text.startswith(PREFIX_AI), "varianta pentru om, nu un răspuns trimis"
    assert decide("cerere_pret", "Cât costă?", "L4", refuz_in_fir=True).actiune == "la_om", "nu insistăm"


def test_ferestrele_de_mesagerie() -> None:
    ora = dt.timedelta(hours=1)
    assert in_fereastra("mesaj", ACUM - 23 * ora, ACUM, scris_de_om=False)[:2] == (True, False)
    assert in_fereastra("mesaj", ACUM - 25 * ora, ACUM, scris_de_om=False)[:2] == (False, False)
    assert in_fereastra("mesaj", ACUM - 25 * ora, ACUM, scris_de_om=True)[:2] == (True, True), "agent uman"
    assert in_fereastra("mesaj", ACUM - 8 * 24 * ora, ACUM, scris_de_om=True)[0] is False
    assert in_fereastra("comentariu", ACUM - 6 * 24 * ora, ACUM, scris_de_om=False)[0] is True
    assert in_fereastra("comentariu", ACUM - ora, ACUM, scris_de_om=True, private_trimise=1)[0] is False
    assert in_fereastra("comentariu", ACUM - 8 * 24 * ora, ACUM, scris_de_om=True)[0] is False
