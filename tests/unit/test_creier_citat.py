"""F4.6 — verificatorul determinist al citatelor (anti-halucinație, docs/09 §9.3). Nucleu pur."""

from decimal import Decimal

import pytest

from app.creier import citat as c
from app.creier.extragere import FaptExtras, valideaza_propunere

PASAJ = (
    "Etiopia Guji, natural, 250 g: 49 lei. Note de afine, miere și iasomie. Potrivită pentru filtru și V60.\n\n"
    "Guatemala Antigua, spălată, 1 kg: 1.138,50 lei; pachetul de 250 g costă 41 lei, cu 12% mai puțin pe kilogram."
)


def verdict(citat: str, numar: str | None = None) -> str | None:
    return c.verifica_propunere(citat, PASAJ, valoare_numar=numar)


def test_un_citat_exact_trece_inclusiv_peste_randuri_noi_si_spatii_multiple() -> None:
    assert verdict("Etiopia Guji, natural, 250 g: 49 lei", "49") is None
    assert verdict("Etiopia   Guji,\n natural, 250 g: 49 lei") is None  # spațiile nu contează
    assert (
        verdict("miere și iasomie. Potrivită pentru filtru și V60.\n\nGuatemala Antigua") is None
    )  # peste paragrafe


def test_un_citat_inventat_sau_imbunatatit_este_respins() -> None:
    assert verdict("Etiopia Guji, natural, 250 g: 39 lei") == "citat_negasit"  # cifra schimbată
    assert verdict("Etiopia Guji este cea mai bună cafea din România") == "citat_negasit"  # inventat
    assert verdict("Etiopia Guji natural 250 g 49 lei") == "citat_negasit"  # fără punctuație: nu e literal
    assert verdict("etiopia guji, natural, 250 g: 49 lei") == "citat_negasit"  # majusculele contează
    assert verdict("Note de afine, miere si iasomie") == "citat_negasit"  # diacriticele contează (și → si)
    assert verdict("Etiopia Guji, natural, 250 g: 49 lei. Livrare gratuită.") == "citat_negasit"  # adaos


def test_citat_prea_scurt_sau_prea_lung() -> None:
    assert (
        verdict("49 lei") == "citat_scurt"
        and verdict("") == "citat_scurt"
        and verdict("       ") == "citat_scurt"
    )
    assert verdict("Etiopia" * 200) == "citat_lung"


def test_cifra_afirmata_trebuie_sa_apara_in_citat() -> None:
    assert verdict("Etiopia Guji, natural, 250 g: 49 lei", "59") == "valoare_absenta_din_citat"
    assert verdict("Etiopia Guji, natural, 250 g: 49 lei", "49.00") is None  # aceeași valoare
    assert verdict("Etiopia Guji, natural, 250 g: 49 lei", "49,0") is None
    assert (
        verdict("Etiopia Guji, natural, 250 g: 49 lei", "4") == "valoare_absenta_din_citat"
    )  # nu subșir de cifre
    assert verdict("Etiopia Guji, natural, 250 g: 49 lei", "abc") == "valoare_invalida"
    assert verdict("pachetul de 250 g costă 41 lei, cu 12% mai puțin", "12") is None
    assert verdict("Guatemala Antigua, spălată, 1 kg: 1.138,50 lei", "1138.5") is None  # format românesc
    assert verdict("Guatemala Antigua, spălată, 1 kg: 1.138,50 lei", "138.5") == "valoare_absenta_din_citat"


def test_normalizari_care_nu_schimba_sensul() -> None:
    sedila = "Guatemala Antigua, spălată, 1 kg"  # litere corecte în pasaj
    assert c.citat_in_text("Șt: ţară ş", "Șt: țară ș")  # sedila e aceeași literă cu virgula
    assert c.citat_in_text("„Guatemala Antigua”, spălată", "„Guatemala Antigua”, spălată") and sedila
    assert c.citat_in_text(
        '"Guatemala Antigua", spălată', "“Guatemala Antigua”, spălată"
    )  # ghilimele tipografice
    assert c.citat_in_text("cafea - proaspătă", "cafea – proaspătă")  # linie lungă
    assert c.citat_in_text("250\xa0g de cafea", "250 g de cafea")  # spațiu nedespărțitor


def test_numerele_din_text_in_forma_canonica() -> None:
    assert c.numere_din("1.200,50 lei și 49,00 lei, 1200.5, 3 kg, 12%, 1 200 lei") == {
        Decimal("1200.5"), Decimal("49"), Decimal("3"), Decimal("12"), Decimal("1200"),
    }  # fmt: skip
    assert c.numere_din("fără cifre") == set()
    assert c.numar_canonic("49,50") == Decimal("49.5") and c.numar_canonic("x") is None


def _fapt(**kw: object) -> FaptExtras:
    baza: dict[str, object] = {
        "tip": "pret", "subiect": "Etiopia Guji", "afirmatie": "Etiopia Guji 250 g costă 49 lei",
        "valoare_numar": "49", "moneda": "RON", "unitate": "250 g", "citat": "Etiopia Guji, natural, 250 g: 49 lei",
    }  # fmt: skip
    return FaptExtras.model_validate({**baza, **kw})


@pytest.mark.parametrize(
    ("campuri", "motiv"),
    [
        ({}, None),
        ({"citat": "Etiopia Guji, natural, 250 g: 39 lei", "valoare_numar": "39"}, "citat_negasit"),
        ({"valoare_numar": "59"}, "valoare_absenta_din_citat"),
        ({"moneda": "lei"}, "moneda_invalida"),
        ({"moneda": "ro"}, "moneda_invalida"),
        ({"afirmatie": "  "}, "afirmatie_invalida"),
        ({"valoare_numar": None, "moneda": None}, None),
    ],
)  # fmt: skip
def test_validarea_unei_propuneri_a_modelului(campuri: dict[str, object], motiv: str | None) -> None:
    assert valideaza_propunere(_fapt(**campuri), PASAJ) == motiv
