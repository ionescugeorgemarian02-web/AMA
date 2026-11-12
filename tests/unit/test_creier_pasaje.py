"""F4.3 — împărțirea în pasaje, normalizarea pentru căutare și fuziunea de ranguri. Nuclee pure."""

from itertools import pairwise

import pytest

from app.creier import pasaje as p
from app.creier.cautare import interogare_text, stem_usor
from tests.vectorizator_fals import vector_bow

PARAGRAF = (
    "Prăjim în loturi mici, de maximum 12 kilograme, pentru ca fiecare pachet să ajungă proaspăt la client. "
)


def test_textul_fiecarui_pasaj_este_exact_felia_din_document_cu_pozitie_si_decalaje() -> None:
    text = "\n\n".join(PARAGRAF * 3 + f"(paragraful {i})" for i in range(12))
    bucati = p.imparte(text, tinta=700, maxim=1000, suprapunere=0)
    assert len(bucati) > 3
    assert [b.pozitie for b in bucati] == list(range(len(bucati)))
    for b in bucati:
        assert b.text == text[b.inceput : b.sfarsit] and 0 <= b.inceput < b.sfarsit <= len(text)
        assert len(b.text) <= 1000
    assert all(a.sfarsit <= b.inceput for a, b in pairwise(bucati))  # fără suprapunere cerută
    assert "".join(b.text for b in bucati).replace("\n", "").replace(" ", "") == text.replace(
        "\n", ""
    ).replace(" ", "")


def test_paragrafele_nu_se_rup_cand_incap_si_pasajele_vecine_se_suprapun_in_unitati_intregi() -> None:
    paragrafe = [f"Paragraful {i}: " + "cuvânt " * 25 for i in range(10)]  # ~190 de caractere fiecare
    text = "\n\n".join(paragrafe)
    bucati = p.imparte(text, tinta=500, maxim=800, suprapunere=250)
    for b in bucati:
        assert b.text.startswith("Paragraful") and b.text.rstrip().endswith(
            "cuvânt"
        )  # tăiat la limite de paragraf
    for a, b in pairwise(bucati):
        assert b.inceput < a.sfarsit  # suprapunere (cel puțin un paragraf)
        assert b.inceput > a.inceput  # dar înaintăm mereu
        assert a.sfarsit - b.inceput <= 250 + 5
    assert bucati[0].inceput == 0 and bucati[-1].sfarsit == len(text.rstrip())


def test_un_paragraf_prea_lung_se_rupe_la_propozitii_apoi_la_cuvinte() -> None:
    propozitii = " ".join(f"Propoziția numărul {i} are destul text ca să conteze." for i in range(60))
    bucati = p.imparte(propozitii, tinta=400, maxim=600, suprapunere=0)
    assert len(bucati) > 4 and all(len(b.text) <= 600 for b in bucati)
    assert all(b.text.endswith(".") for b in bucati)  # tăiat la capăt de propoziție
    uriasa = "cuvânt " * 1000
    bucati = p.imparte(uriasa, tinta=400, maxim=600, suprapunere=0)
    assert all(len(b.text) <= 600 and not b.text.startswith(" ") for b in bucati) and len(bucati) >= 12


def test_cazuri_limita() -> None:
    assert p.imparte("") == [] and p.imparte("   \n\n  ") == [] and p.imparte("---") == []
    [b] = p.imparte("Un singur paragraf scurt.")
    assert (b.pozitie, b.inceput, b.sfarsit) == (0, 0, 25)
    with pytest.raises(ValueError):
        p.imparte("x", tinta=100, maxim=50)
    with pytest.raises(ValueError):
        p.imparte("x", tinta=100, maxim=200, suprapunere=100)


def test_impartirea_este_deterministica() -> None:
    text = "\n\n".join(PARAGRAF * (i % 4 + 1) for i in range(30))
    assert p.imparte(text) == p.imparte(text)


def test_normalizarea_scoate_diacriticele_si_unifica_formele_s_t_cu_sedila_si_virgula() -> None:
    for forma in ("șt", "şt", "st", "ŞT", "ȘT"):
        assert p.normalizeaza(forma) == "st"
    assert p.normalizeaza("țară ţară tara") == "tara tara tara"
    assert p.normalizeaza("Cât costă cafeaua, în lei? 49 lei!") == "cat costa cafeaua in lei 49 lei"
    assert p.normalizeaza("Ăă Îî Ââ") == "aa ii aa"


def test_jetoanele_scot_cuvintele_de_legatura_si_pastreaza_ordinea_fara_duplicate() -> None:
    assert p.jetoane("Cât costă cafeaua din Etiopia Guji și cafeaua din Columbia?") == [
        "costa", "cafeaua", "etiopia", "guji", "columbia",
    ]  # fmt: skip
    assert p.jetoane("") == [] and p.jetoane("și de la în") == []


def test_interogarea_de_text_foloseste_prefixe_pentru_cuvintele_lungi() -> None:
    assert (
        stem_usor("cafeaua") == "cafea" and stem_usor("pret") == "pret" and stem_usor("livrarea") == "livrar"
    )
    assert interogare_text(["costa", "cafeaua", "guji"]) == "costa | cafea:* | guji"
    assert interogare_text([]) == ""


def test_fuziunea_de_ranguri_combina_clasamentele_si_este_deterministica() -> None:
    clas = {"vector": ["a", "b", "c", "d"], "text": ["b", "a", "e"], "trigrame": ["b", "e"]}
    f = p.fuzioneaza(clas)
    assert [e for e, _, _ in f] == ["b", "a", "e", "c", "d"]  # b apare sus peste tot
    assert f[0][2] == {"vector": 2, "text": 1, "trigrame": 1}
    assert f == p.fuzioneaza({k: list(v) for k, v in clas.items()})
    # un element prezent doar într-un clasament poate câștiga dacă e primul acolo și clasamentele nu se bat cap în cap
    assert p.fuzioneaza({"x": ["a"], "y": ["b"]})[0][0] == "a"  # egalitate de scor: ordinea alfabetică
    assert p.fuzioneaza({"x": ["a", "a", "b"]}) == [
        ("a", round(1 / 61, 12), {"x": 1}),
        ("b", round(1 / 63, 12), {"x": 3}),
    ]
    assert p.fuzioneaza({}) == [] and p.fuzioneaza({"x": []}) == []


def test_ponderile_schimba_ordinea() -> None:
    clas = {"vector": ["a", "b"], "text": ["b", "a"]}
    assert p.fuzioneaza(clas, ponderi={"vector": 2.0})[0][0] == "a"
    assert p.fuzioneaza(clas, ponderi={"text": 2.0})[0][0] == "b"


def test_vectorizatorul_fals_pastreaza_apropierea_si_este_determinist() -> None:
    def cos(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    q = vector_bow("Cât costă cafeaua Etiopia Guji?")
    aproape = vector_bow("Etiopia Guji, natural, 250 g: 49 lei. Cafeaua costă 49 lei.")
    departe = vector_bow("Parcare: în fața cafenelei există patru locuri cu plată.")
    assert cos(q, aproape) > 0.3 > cos(q, departe) and abs(cos(q, q) - 1) < 1e-3
    assert vector_bow("text") == vector_bow("text") and len(q) == 384
    assert cos(vector_bow("prăjim cafeaua"), vector_bow("prajim cafeaua")) > 0.99  # diacriticele nu contează
