"""F5.3 — extragerea deterministă a afirmațiilor și acoperirea lor de către registru (G2). Nucleele pure."""

from decimal import Decimal as D

import pytest

from app.validare import acoperire as ac
from app.validare import afirmatii
from app.validare.acoperire import Acoperire
from app.validare.verifica_fapte import fapte_lipsa, probleme_afirmatii


def tipuri(text: str) -> list[tuple[str, str]]:
    return [(a.tip, a.fragment) for a in afirmatii.extrage(text)]


# --- extragere --------------------------------------------------------------------------------------------
# ----------------


def test_preturi_cu_moneda_si_numere_romanesti() -> None:
    a = afirmatii.extrage("Costă 49 lei, sau 1.200,50 RON, ori 12,5 euro, sau € 30, ori 5 USD.")
    assert [(x.valoare, x.moneda) for x in a if x.tip == "pret"] == [
        (D("49"), "RON"), (D("1200.5"), "RON"), (D("12.5"), "EUR"), (D("30"), "EUR"), (D("5"), "USD")
    ]  # fmt: skip
    assert all(x.fragment in "Costă 49 lei, sau 1.200,50 RON, ori 12,5 euro, sau € 30, ori 5 USD." for x in a)


def test_procente_termene_date_ore_si_cifre() -> None:
    t = "Reducere 20% la livrare în 2-3 zile. Sâmbătă la 9:30, pe 15 decembrie 2026 sau 1.12.2026. Din 2019 avem 12 angajați."
    gasite = tipuri(t)
    assert ("procent", "20%") in gasite
    assert [f for tip, f in gasite if tip == "termen"] == ["2-3 zile", "2-3 zile"]
    assert ("ora", "9:30") in gasite
    assert (
        ("data", "15 decembrie 2026") in gasite
        and ("data", "1.12.2026") in gasite
        and ("data", "Din 2019") in gasite
    )
    assert ("cifra", "12") in gasite
    ora = next(a for a in afirmatii.extrage(t) if a.tip == "ora")
    assert ora.ora == "09:30"


def test_fragmentul_este_exact_din_text_inclusiv_cu_majuscule_si_diacritice() -> None:
    t = "CEL MAI BUN prăjitor, GARANTĂM gustul!"
    a = afirmatii.extrage(t)
    assert [(x.tip, x.fragment) for x in a] == [("superlativ", "CEL MAI BUN"), ("promisiune", "GARANTĂM")]
    assert all(t[x.start : x.sfarsit] == x.fragment for x in a)


def test_superlative_comparatii_si_promisiuni_din_liste() -> None:
    assert ("superlativ", "cea mai bună") in tipuri("Este cea mai bună cafea din oraș.")
    assert ("superlativ", "numărul 1") in tipuri("Suntem numărul 1 în Brașov.")
    assert ("comparatie", "mai ieftin decât") in tipuri("Mai ieftin decât la supermarket.") or (
        "comparatie",
        "Mai ieftin decât",
    ) in tipuri("Mai ieftin decât la supermarket.")
    assert any(t == "comparatie" for t, _ in tipuri("Spre deosebire de alții, prăjim zilnic."))
    assert any(t == "promisiune" for t, _ in tipuri("Livrare gratuită în toată țara. Banii înapoi oricând."))
    assert tipuri("cel mai probabil vei plăti mai târziu") == []


def test_ce_nu_este_afirmatie_despre_client() -> None:
    assert tipuri("Vezi https://zorilor.ro/p123 și #cafea2024, scrie la office@zorilor.ro.") == []
    assert tipuri("3 pași simpli pentru o cafea bună. Top 5 sfaturi.") == [], (
        "liste de sfaturi nu sunt afirmații"
    )
    assert tipuri("În 2024 am început.") == [], "un an singur nu e o afirmație (doar «din 2019»)"
    assert tipuri("1. Alege boabele\n2. Macină-le\n3. Prepară") == [], "numerotarea listelor"
    assert tipuri("Cafea bună în fiecare dimineață.") == []


def test_extragerea_este_la_fel_pe_text_fara_diacritice() -> None:
    cu = tipuri("Garantăm livrare gratuită în 24 de ore, la 49 lei.")
    fara = tipuri("Garantam livrare gratuita in 24 de ore, la 49 lei.")
    assert [t for t, _ in cu] == [t for t, _ in fara]


# --- acoperire --------------------------------------------------------------------------------------------
# -------------------


@pytest.fixture
def reg() -> ac.Registru:
    return ac.Registru(
        (
            ac.intrare_din_texte(
                "o1", "oferta", "Abonament Lunar", ["Livrare gratuită în toată țara", "Garanție: schimbăm cafeaua"],
                tip="oferta", pret=(D(89), "RON"),
            ),
            ac.intrare_din_texte(
                "o2", "oferta", "Pachet Etiopia Guji 250 g", ["Cafea de specialitate"], tip="oferta",
                pret=(D(49), "RON"), pret_referinta=(D(59), "RON"),
            ),
            ac.intrare_din_texte(
                "f1", "fapt", "Program degustare", ["Sâmbătă la 11:00 degustare gratuită, pe 15 decembrie 2026"],
                tip="program",
            ),
            ac.intrare_din_texte("f2", "fapt", "Livrare", ["Livrăm în 2-3 zile lucrătoare"], tip="termen"),
            ac.intrare_din_texte("f3", "fapt", "Istoric", ["Prăjim cafea din 2019, 12 angajați"], tip="cifra"),
        )
    )  # fmt: skip


def stari(text: str, reg: ac.Registru) -> list[tuple[str, Acoperire]]:
    return [(c.afirmatie.fragment, c.acoperire) for c in ac.verifica(text, reg)]


def test_pretul_corect_trece_cel_gresit_este_diferit_cel_necunoscut_neacoperit(reg: ac.Registru) -> None:
    assert stari("Abonamentul Lunar costă 89 lei.", reg) == [("89 lei", Acoperire.ACOPERITA)]
    [(_, a)] = stari("Abonamentul Lunar costă 59 lei.", reg)
    assert a is Acoperire.DIFERITA
    c = ac.verifica("Abonamentul Lunar costă 59 lei.", reg)[0]
    assert "Abonament Lunar" in c.registru_spune and "89" in c.registru_spune
    assert stari("Un produs fără nume costă 123 lei.", reg) == [("123 lei", Acoperire.NEACOPERITA)]


def test_un_pret_real_dar_al_altui_produs_este_diferit(reg: ac.Registru) -> None:
    assert stari("Abonamentul Lunar costă 49 lei.", reg)[0][1] is Acoperire.DIFERITA


def test_moneda_conteaza_si_lei_este_ron(reg: ac.Registru) -> None:
    assert stari("Abonamentul Lunar: 89 RON.", reg)[0][1] is Acoperire.ACOPERITA
    assert stari("Abonamentul Lunar: 89 euro.", reg)[0][1] is Acoperire.DIFERITA


def test_pretul_de_referinta_se_accepta_doar_ca_pret_anterior(reg: ac.Registru) -> None:
    pachet = "Pachetul Etiopia Guji 250 g"
    assert stari(f"{pachet} costă 59 lei.", reg)[1][1] is Acoperire.DIFERITA
    assert [a for _, a in stari(f"{pachet}: 49 lei în loc de 59 lei.", reg)] == [Acoperire.ACOPERITA] * 3


def test_reducerea_se_calculeaza_din_pret_si_pret_de_referinta(reg: ac.Registru) -> None:
    pachet = "Pachetul Etiopia Guji 250 g: 49 lei în loc de 59 lei"
    assert [a for f, a in stari(pachet + ", reducere 17%.", reg) if f == "17%"] == [Acoperire.ACOPERITA]
    [a] = [a for f, a in stari(pachet + ", reducere 30%.", reg) if f == "30%"]
    assert a is Acoperire.DIFERITA
    assert [a for f, a in stari("Reducere 50% la tot.", reg)] == [Acoperire.NEACOPERITA]


def test_termene_date_ore_si_cifre(reg: ac.Registru) -> None:
    assert [a for _, a in stari("Livrăm în 2-3 zile.", reg)] == [Acoperire.ACOPERITA] * 2
    assert stari("Livrăm în 24 de ore.", reg)[0][1] is Acoperire.NEACOPERITA
    assert stari("Degustare la 11:00 pe 15 decembrie 2026.", reg)[0][1] is Acoperire.ACOPERITA
    assert [a for _, a in stari("Degustare la 12:00 pe 16 decembrie 2026.", reg)][:2] == [
        Acoperire.NEACOPERITA, Acoperire.NEACOPERITA
    ]  # fmt: skip
    assert [a for _, a in stari("Din 2019 prăjim, avem 12 angajați.", reg)] == [Acoperire.ACOPERITA] * 2
    assert stari("Avem 40 de angajați.", reg)[0][1] is Acoperire.NEACOPERITA


def test_superlativele_comparatiile_si_promisiunile_cer_un_fapt_care_le_spune(reg: ac.Registru) -> None:
    assert stari("Cel mai bun prăjitor din oraș.", reg) == [("Cel mai bun", Acoperire.NEACOPERITA)]
    assert stari("Livrare gratuită în toată țara.", reg)[0][1] is Acoperire.ACOPERITA
    assert stari("Garantăm gustul.", reg)[0][1] is Acoperire.ACOPERITA, "faptul «Garanție» acoperă «garantăm»"
    assert stari("Banii înapoi oricând.", reg)[0][1] is Acoperire.NEACOPERITA
    cu_premiu = ac.Registru(
        (
            *reg.intrari,
            ac.intrare_din_texte("f9", "fapt", "Premii", ["Am primit premiul pentru cel mai bun espresso"]),
        )
    )
    assert stari("Cel mai bun prăjitor.", cu_premiu)[0][1] is Acoperire.ACOPERITA


def test_registrul_gol_nu_acopera_nimic() -> None:
    gol = ac.Registru(())
    assert {a for _, a in stari("Costă 10 lei, livrăm în 2 zile, cel mai bun.", gol)} == {
        Acoperire.NEACOPERITA
    }


def test_cifrele_se_compara_exact_nu_aproximativ(reg: ac.Registru) -> None:
    assert stari("Abonamentul Lunar costă 89,01 lei.", reg)[0][1] is Acoperire.DIFERITA
    assert stari("Abonamentul Lunar costă 89,00 lei.", reg)[0][1] is Acoperire.ACOPERITA, "89 = 89,00"


# --- problemele și faptele lipsă
# ----------------------------------------------------------------------------------------------


def test_o_afirmatie_repetata_se_raporteaza_o_data(reg: ac.Registru) -> None:
    p = probleme_afirmatii("Cel mai bun! Cel mai bun din oraș.", reg)
    assert [x.regula for x in p] == ["G2.neacoperita.superlativ"]
    assert p[0].fragment == "Cel mai bun" and "registrul de fapte" in p[0].instructiune


def test_pret_diferit_are_regula_proprie_si_spune_ce_zice_registrul(reg: ac.Registru) -> None:
    [p] = probleme_afirmatii("Abonamentul Lunar costă 59 lei.", reg)
    assert p.regula == "G2.pret_diferit" and "89" in p.instructiune and p.fragment == "59 lei"


def test_faptele_lipsa_se_gasesc_dupa_tip_si_subiect(reg: ac.Registru) -> None:
    nec = [
        {"tip": "pret", "subiect": "Abonament Lunar"},  # există
        {"tip": "pret", "subiect": "Abonament Birou"},  # lipsește
        {"tip": "termen", "subiect": "Livrare"},  # există
        {"tip": "garantie", "subiect": "Returnare"},  # lipsește
    ]
    lipsa = fapte_lipsa(reg, nec, ["  ", "Care este adresa cafenelei?"])
    assert [(t, s) for _, t, s in lipsa] == [
        ("pret", "Abonament Birou"),
        ("garantie", "Returnare"),
        (None, None),
    ]
    assert (
        "prețul" in lipsa[0][0]
        and "Abonament Birou" in lipsa[0][0]
        and lipsa[2][0] == "Care este adresa cafenelei?"
    )
    assert fapte_lipsa(reg, [], []) == []
