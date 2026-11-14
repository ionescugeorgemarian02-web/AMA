"""F10.5 — frazele raportului și controlul „G2 pe cifre”: niciun număr din text care nu vine din date."""

from typing import Any

from app.analiza import raport_cifre

CIFRE: dict[str, Any] = {
    "postari_publicate": 9,
    "postari_masurate": 8,
    "totaluri": {"afisari": 12400, "aprecieri": 610, "comentarii": 45},
    "top": [{"livrabil_id": "x", "canal": "facebook", "tipar_hook": "întrebare", "la_suta": 8.0}],
    "tipare": [
        {"valoare": "întrebare", "postari": 3, "la_suta": 7.3},
        {"valoare": "cifră", "postari": 2, "la_suta": 2.5},
    ],
    "sloturi": [{"valoare": "marți, ora 09", "postari": 4, "la_suta": 6.1}],
}


def test_frazele_vin_din_cifre_si_trec_controlul() -> None:
    t = raport_cifre.propozitii(CIFRE)
    assert t["rezultate"] == (
        "Am măsurat 8 din 9 postări publicate. În total: 12400 afișări, 610 aprecieri, 45 comentarii."
    )
    assert "„întrebare”: în medie 7,3 interacțiuni la 100 de afișări, din 3 postări" in t["ce_a_mers"]
    assert "„cifră”: în medie 2,5 interacțiuni" in t["ce_nu_a_mers"]
    assert "marți, ora 09: în medie 6,1 interacțiuni la 100 de afișări, din 4 postări" in t["public"]
    assert raport_cifre.verifica(t, CIFRE) == []


def test_un_numar_care_nu_vine_din_date_este_prins() -> None:
    t = raport_cifre.propozitii(CIFRE)
    t["rezultate"] = t["rezultate"].replace("12400 afișări", "15000 afișări")
    t["ce_a_mers"] += " Am crescut cu 40% față de luna trecută."
    probleme = raport_cifre.verifica(t, CIFRE)
    assert len(probleme) == 2
    assert any("15000" in p for p in probleme) and any("40" in p for p in probleme)


def test_fara_grupuri_destule_fraza_spune_asta() -> None:
    c = {**CIFRE, "tipare": [], "sloturi": []}
    t = raport_cifre.propozitii(c)
    assert "nu sunt destule postări" in t["ce_a_mers"] and "nu sunt destule postări" in t["public"]
    assert raport_cifre.verifica(t, c) == []
    unul = {**CIFRE, "tipare": CIFRE["tipare"][:1]}
    assert "nu avem încă termen de comparație" in raport_cifre.propozitii(unul)["ce_nu_a_mers"]


def test_fara_postari_masurate_nu_exista_cifre() -> None:
    c = {
        "postari_publicate": 2,
        "postari_masurate": 0,
        "totaluri": {},
        "top": [],
        "tipare": [],
        "sloturi": [],
    }
    t = raport_cifre.propozitii(c)
    assert "Nicio postare măsurată" in t["rezultate"] and t["ce_a_mers"] == ""
    assert raport_cifre.verifica(t, c) == []
