"""F5.2 — G10 Limbă: nucleul pur (diacritice lipsă, sedilă, î / â, tipografie) și datele lui."""

import datetime as dt
import uuid

import pytest

from app.validare import limba, text_ro
from app.validare.date_validare import incarca
from app.validare.intrare import Continut, Intrare, SituatieLivrabil
from app.validare.verdict import Rezultat, Severitate

BUN = (
    "Cafeaua proaspătă ajunge la tine în cel mult zece zile de la prăjire. Dacă nu îți place, o schimbăm fără alte "
    "întrebări, iar abonamentul îl poți opri oricând, chiar și în ziua comenzii."
)
FARA = (
    "Cafeaua proaspata ajunge la tine in cel mult zece zile de la prajire. Daca nu iti place, o schimbam fara alte "
    "intrebari, iar abonamentul il poti opri oricand, chiar si in ziua comenzii."
)


def reguli(text: str) -> list[str]:
    return [p.regula for p in limba.probleme_limba(text)]


def verdict(text: str):  # type: ignore[no-untyped-def]
    sit = SituatieLivrabil(uuid.uuid4(), uuid.uuid4(), "postare", "facebook", 1, 0)
    return limba.g10_reguli(Intrare(sit, Continut(1, text), dt.datetime(2026, 11, 13, tzinfo=dt.UTC)))


def test_dictionarul_de_cuvinte_este_coerent() -> None:
    dic = incarca("limba")["cuvinte_frecvente_fara_diacritice"]
    assert len(dic) >= 150
    for fara, cu in dic.items():
        assert fara == text_ro.fara_diacritice(cu).lower(), fara
        assert cu.lower() != fara, f"{fara}: forma corectă nu diferă"
    for ambiguu in ("pana", "mana", "limba", "apa", "seara", "vara", "comanda", "va", "firma", "sigura"):
        assert ambiguu not in dic, f"{ambiguu} este și un cuvânt românesc fără diacritice"


def test_textul_corect_cu_diacritice_nu_are_probleme() -> None:
    assert reguli(BUN) == []
    assert verdict(BUN).rezultat is Rezultat.TRECE


def test_textul_fara_diacritice_este_respins_cu_exemple() -> None:
    v = verdict(FARA)
    assert v.rezultat is Rezultat.ESEC and v.severitate is Severitate.MAJORA
    assert v.dovezi[0].regula == "G10.diacritice_lipsa"
    assert "„in” → „în”" in v.instructiune or "„iti” → „îți”" in v.instructiune or "→" in v.instructiune


def test_un_text_lung_fara_nicio_diacritica_este_respins_chiar_daca_dictionarul_nu_l_prinde() -> None:
    text = (
        "Cafea de specialitate din boabe proaspete pentru fiecare dimineata. Livram pachete lunare oriunde."
        * 2
    )
    assert [c for c in text if c in "ăâîșț"] == []
    assert "G10.diacritice_lipsa" in reguli(text)
    assert verdict(text).blocheaza


def test_o_singura_greseala_din_dictionar_este_doar_avertisment() -> None:
    v = verdict(BUN.replace("în cel mult", "in cel mult"))
    assert v.rezultat is Rezultat.AVERTISMENT and v.severitate is Severitate.MAJORA
    assert "„in” → „în”" in v.instructiune
    assert verdict(BUN.replace("în cel mult", "in cel mult").replace("fără", "fara")).blocheaza, (
        "două greșeli blochează"
    )


def test_majusculele_si_siglele_nu_sunt_confundate() -> None:
    assert reguli(
        "PRET MIC la TVA si USA, doar azi la Cafeneaua Zorilor din Brașov și în țară, pentru tine."
    ) == ["G10.diacritice_lipsa"], "doar «si» din dicționar; «PRET» (majuscule) nu se judecă"
    assert "Preț" in "".join(
        p.instructiune for p in limba.probleme_limba("Pret mic pentru tine azi, în țară.")
    )


def test_sedila_este_avertisment_iar_corectia_exista() -> None:
    cu_sedila = BUN.replace("ș", "ş").replace("ț", "ţ")
    assert "ş" in cu_sedila
    p = limba.probleme_limba(cu_sedila)
    assert [x.regula for x in p] == ["G10.sedila"] and not p[0].blocant
    assert verdict(cu_sedila).rezultat is Rezultat.AVERTISMENT
    assert (
        limba.corecteaza_sedila(cu_sedila) == BUN
        and limba.corecteaza_sedila("Şcoală, Ţară") == "Școală, Țară"
    )
    assert reguli(limba.corecteaza_sedila(cu_sedila)) == []


@pytest.mark.parametrize(
    ("text", "gresit"),
    [("Cînd vii la noi?", True), ("Sunt mândru de rezultat.", False), ("Gândul meu îți aparține.", False),
     ("Am fost âmpreună.", True), ("Neînțelesul a rămas.", False), ("Reîncepem luni.", False), ("A coborî scările.", False),
     ("Pămînt bun", True)],
)  # fmt: skip
def test_i_si_a(text: str, gresit: bool) -> None:
    assert ("G10.i_sau_a" in reguli(text)) is gresit


def test_tipografie_ghilimele_cratima_repetitii() -> None:
    assert reguli(BUN + " Spune „da”.") == []
    assert "G10.ghilimele" in reguli(BUN + ' Spune "da".')
    assert "G10.cratima" in reguli(BUN + " Vino azi - nu mâine.")
    assert reguli(BUN + " Vino-n grabă, la-ntâlnire.") == []
    assert "G10.repetitie" in reguli(BUN + " Cafea cafea bună.")
    assert reguli("Vezi https://zorilor.ro/abonament-lunar și ce urmează, la fel ca ieri la ora zece.") == []


def test_tipografia_este_un_singur_avertisment_minor() -> None:
    v = verdict(BUN + ' Vino azi - acum acum "da".')
    assert v.rezultat is Rezultat.AVERTISMENT and v.severitate is Severitate.MINORA
    assert len(v.dovezi) == 3 and v.scor > 0.8


def test_probleme_nu_modifica_cifrele_si_nu_cer_schimbari_de_fapte() -> None:
    p = limba.probleme_limba(
        "Abonamentul Lunar costa 89 lei pe luna, iar pachetul de 250 g costa 49 lei, in orice zi."
    )
    assert all("89" not in x.instructiune and "49" not in x.instructiune for x in p)
