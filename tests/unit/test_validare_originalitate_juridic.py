"""F5.6 — G7 Originalitate și G9 Juridic: nucleele pure (shingle-uri, istoric de prețuri, reduceri, promisiuni, active)."""

import datetime as dt
from decimal import Decimal as D

from app.validare import juridic, originalitate
from app.validare.date_validare import incarca
from app.validare.intrare import Continut

SURSA = (
    "Cafeaua noastră de specialitate este prăjită în loturi mici la Brașov și ajunge la tine în cel mult zece zile "
    "de la prăjire, iar dacă nu îți place o schimbăm fără alte întrebări."
)


def sh(text: str) -> set[int]:
    return set(originalitate.shingles([c for c, _, _ in originalitate.cuvinte_cu_pozitii(text)], 5))


def test_textul_copiat_are_suprapunere_mare_cu_fragmentul_exact() -> None:
    copie = "Salut! " + SURSA + " Vino la degustare."
    s = originalitate.suprapunere(copie, [sh(SURSA)], 5)
    assert s.containment > 0.7 and s.rand_maxim >= 25
    assert s.fragment == SURSA.rstrip(".") and s.fragment in copie, (
        "fragmentul e exact din text, cu diacritice"
    )


def test_textul_original_nu_se_suprapune() -> None:
    s = originalitate.suprapunere(
        "Vino sâmbătă la degustare și află cum se prepară un espresso bun acasă, fără aparate.",
        [sh(SURSA)],
        5,
    )
    assert s.containment == 0.0 and s.rand_maxim == 0 and s.fragment == ""


def test_potrivirea_ignora_diacriticele_majusculele_si_punctuatia() -> None:
    s = originalitate.suprapunere(SURSA.upper().replace("Ă", "A").replace(",", ""), [sh(SURSA)], 5)
    assert s.containment > 0.9


def test_o_sursa_nereutilizabila_blocheaza_la_prag_mic_una_a_clientului_doar_la_copie_integrala() -> None:
    parte = originalitate.Suprapunere(0.35, 8, "un fragment")
    assert originalitate.probleme_suprapunere(parte, sursa="Concurent", nereutilizabila=True)[0].blocant
    assert originalitate.probleme_suprapunere(parte, sursa="Site client", nereutilizabila=False) == []
    integral = originalitate.Suprapunere(0.8, 50, "mult text")
    p = originalitate.probleme_suprapunere(integral, sursa="Site client", nereutilizabila=False)
    assert p and not p[0].blocant
    lung = originalitate.Suprapunere(0.1, 20, "un rând lung copiat")
    assert originalitate.probleme_suprapunere(lung, sursa="Concurent", nereutilizabila=True), (
        "un rând lung blochează și cu prag mic"
    )


def test_activul_fara_licenta_este_semnalat() -> None:
    p = originalitate.probleme_active(
        ({"nume": "poza-1.jpg", "licenta": "CC0"}, {"nume": "poza-2.jpg"}, {"nume": "x", "licenta": " "})
    )
    assert [x.fragment for x in p] == ["poza-2.jpg", "x"] and all(x.blocant for x in p)


def test_datele_g7_g9_sunt_valide() -> None:
    assert (
        incarca("originalitate")["prag"]["nereutilizabila"]["containment"]
        < incarca("originalitate")["prag"]["reutilizabila"]["containment"]
    )
    assert (
        incarca("juridic")["pret_referinta"]["zile"] == 30
        and incarca("juridic")["promisiuni_rezultat"]["expresii"]
    )


# --- G9 ----------------------------------------------------------------------------------------------------------------------------

AZI = dt.datetime(2026, 11, 12, 12, tzinfo=dt.UTC)


def d(zile: int) -> dt.datetime:
    return AZI - dt.timedelta(days=zile)


def test_pretul_minim_din_ultimele_30_de_zile() -> None:
    istoric = [
        juridic.VersiunePret(D(70), d(60), d(20)),
        juridic.VersiunePret(D(60), d(20), d(1)),
        juridic.VersiunePret(D(49), d(1), None),
    ]
    assert juridic.pret_minim_anterior(istoric, d(1), 30) == (D(60), True)
    doar_vechi = [
        juridic.VersiunePret(D(55), d(90), d(40)),
        juridic.VersiunePret(D(70), d(40), d(1)),
        juridic.VersiunePret(D(49), d(1), None),
    ]
    assert juridic.pret_minim_anterior(doar_vechi, d(1), 30) == (D(70), True), (
        "55 e în afara ferestrei de 30 de zile"
    )


def test_istoric_inexistent_sau_partial_este_spus_explicit() -> None:
    assert juridic.pret_minim_anterior([juridic.VersiunePret(D(49), d(1), None)], d(1), 30) == (None, False)
    assert juridic.pret_minim_anterior([], d(1), 30) == (None, False)
    scurt = [juridic.VersiunePret(D(70), d(10), d(1)), juridic.VersiunePret(D(49), d(1), None)]
    assert juridic.pret_minim_anterior(scurt, d(1), 30) == (D(70), False)


def test_afirmatiile_de_reducere() -> None:
    assert [a.fragment for a in juridic.afirmatii_de_reducere("Reducere 30% azi!")] == ["30%"]
    assert [a.fragment for a in juridic.afirmatii_de_reducere("Doar azi: -20% la tot")] == ["20%"]
    assert juridic.afirmatii_de_reducere("Cafea cu 10% mai puțină cofeină") == []


def test_promisiunile_de_rezultat_blocheaza() -> None:
    for t in (
        "Rezultate garantate în 7 zile.",
        "Sigur vei slăbi cu cura noastră.",
        "Promitem că vei câștiga mai mult.",
        "Succes garantat!",
    ):
        assert juridic.probleme_promisiuni(t), t
    assert juridic.probleme_promisiuni("Cafea proaspătă, prăjită azi, pentru tine.") == []
    assert juridic.probleme_promisiuni("Rezultate garantate")[0].fragment == "Rezultate garantate"


def test_continutul_expune_active_ca_tuplu() -> None:
    assert Continut(1, "x", active=({"nume": "a"},)).active == ({"nume": "a"},)
