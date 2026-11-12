"""F3.6 — criteriile automate și setul de sarcini (date în repo)."""

import collections

import pytest

from app.gateway import criterii, evaluare
from app.gateway.profiluri import PROFILURI


def test_setul_are_72_de_sarcini_reale_cate_12_pe_fiecare_profil_din_8_2() -> None:
    sarcini = evaluare.incarca_sarcini()
    assert 60 <= len(sarcini) <= 100 and len(sarcini) == 72
    pe_profil = collections.Counter(s.profil for s in sarcini)
    assert set(pe_profil) == {p.nume for p in PROFILURI} and set(pe_profil.values()) == {12}
    assert evaluare.valideaza_sarcini(sarcini) == []
    assert len({s.intrare + s.instructiune for s in sarcini}) == 72  # nicio sarcină dublată
    # fiecare sarcină cere ceva verificabil și are textul în română (cel puțin un semn diacritic în instrucțiune sau intrare)
    assert all(any(c in "ăâîșț" for c in s.instructiune + s.intrare) for s in sarcini)


def test_schemele_si_prompturile_de_evaluare_corespund_profilurilor() -> None:
    assert set(evaluare.SCHEME) == {p.nume for p in PROFILURI}
    fisiere = sorted(p.name for p in (evaluare.DIRECTOR / "prompturi").glob("*.md"))
    assert fisiere == sorted(f"evaluare.{p.nume}.v1.md" for p in PROFILURI)


def test_amprenta_setului_se_schimba_cand_se_schimba_o_sarcina() -> None:
    sarcini = evaluare.incarca_sarcini()
    a = evaluare.amprenta_set(sarcini)
    assert a == evaluare.amprenta_set(sarcini) and len(a) == 64
    assert a != evaluare.amprenta_set(sarcini[:-1])


def test_ieșire_invalida_are_scor_zero_si_una_perfecta_unu() -> None:
    c = {"raspuns_exact": {"camp": "eticheta", "valoare": "negativ"}}
    assert criterii.evalueaza(c, None).scor == 0.0
    assert criterii.evalueaza(c, {"eticheta": "Negativ "}).scor == 1.0  # majuscule și spații nu contează
    assert criterii.evalueaza(c, {"eticheta": "pozitiv"}).scor == 0.5  # schema e validă, răspunsul nu


def test_cuvinte_lungime_si_interzise() -> None:
    c = {"text_din": "text", "lungime_min": 10, "lungime_max": 40, "cuvinte_obligatorii": ["ceai rece", "mentă"],
         "cuvinte_interzise": ["garantat"]}  # fmt: skip
    ok = criterii.evalueaza(
        c, {"text": "Un ceai rece cu menta proaspătă"}
    )  # „menta” fără diacritică tot se găsește
    assert ok.scor == 1.0 and ok.detalii["cuvinte_obligatorii"] == 1.0
    prost = criterii.evalueaza(c, {"text": "Garantat: ceai"})
    assert prost.detalii["cuvinte_interzise"] == 0.0 and prost.detalii["cuvinte_obligatorii"] == 0.0
    assert criterii.evalueaza(c, {"text": "x" * 41}).detalii["lungime_max"] == 0.0
    jumatate = criterii.evalueaza({"cuvinte_obligatorii": ["a1", "b2"]}, {"text": "a1 doar"})
    assert jumatate.detalii["cuvinte_obligatorii"] == 0.5


@pytest.mark.parametrize(
    ("text", "corect"),
    [
        ("Vă așteptăm în fiecare zi, într-o atmosferă plăcută pentru toți clienții noștri din țară.", True),
        ("Va asteptam in fiecare zi, intr-o atmosfera placuta pentru toti clientii nostri din tara.", False),
        (
            "Vă aşteptăm în fiecare zi, într-o atmosferă plăcută pentru toți clienții noștri.",
            False,
        ),  # cedilă ş
        ("Oferta e valabilă și azi, după ora zece, în magazin.", True),
        (
            "Ofertă valabilă si azi, dupa ora zece, în magazin, pentru toți cei din oraș.",
            False,
        ),  # „si”, „dupa”
        ("Ok.", True),  # un text scurt nu cere semne diacritice
    ],
)
def test_diacriticele_corecte(text: str, corect: bool) -> None:
    assert criterii.diacritice_corecte(text) is corect


def test_scorul_pe_profil_combina_automatul_cu_nota_umana() -> None:
    assert criterii.scor_profil([], [], 0.4) is None
    assert criterii.scor_profil([1.0, 0.5], [], 0.4) == 0.75
    assert criterii.scor_profil([1.0], [1], 0.4) == 0.6  # nota 1 = 0, nota 5 = 1
    assert criterii.scor_profil([0.5], [5, 5], 0.4) == 0.7
