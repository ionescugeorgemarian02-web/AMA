"""F4.1 — compartimentele ca date (docs/10 §10.1–10.2) și diferența dintre versiuni."""

from pydantic import BaseModel

from app.creier import (
    COMPARTIMENTE,
    Compartiment,
    ContinutInvalid,
    Fel,
    Nivel,
    Schimbare,
    diferenta,
    inregistreaza_schema,
    valideaza_continut,
)
from app.creier.compartimente import _SCHEME, text_de_cautare


def test_cele_zece_compartimente_din_10_1_exista_ca_date() -> None:
    # cele zece din 10.1 + cele trei adăugate în F4 (D-005: brief, insight de piață, strategie)
    adaugate = {Compartiment.BRIEF, Compartiment.INSIGHT_PIATA, Compartiment.STRATEGIE}
    assert len(COMPARTIMENTE) == 13 and set(COMPARTIMENTE) == set(Compartiment)
    assert len(set(Compartiment) - adaugate) == 10
    assert all(i.nume and i.contine and i.cine_schimba and i.niveluri for i in COMPARTIMENTE.values())
    # tot ce e al clientului are nivelul „client”; nișa și platforma sunt doar pentru tipare agregate
    assert all(Nivel.CLIENT in i.niveluri for i in COMPARTIMENTE.values())
    assert Nivel.PLATFORMA in COMPARTIMENTE[Compartiment.PLAYBOOK].niveluri
    assert COMPARTIMENTE[Compartiment.PROFIL_BRAND].niveluri == {Nivel.CLIENT}


def test_doar_compartimentele_automate_accepta_aprobarea_de_sistem() -> None:
    automate = {c for c, i in COMPARTIMENTE.items() if i.aprobare_sistem}
    assert automate == {
        Compartiment.EXEMPLE_AUR,
        Compartiment.EXEMPLE_NEGATIVE,
        Compartiment.INSIGHT_PUBLIC,
        Compartiment.INSIGHT_PIATA,  # afirmațiile concurenței, după verificarea citatului (F4.10)
        Compartiment.MEMORIE_PERFORMANTA,
    }
    for c in (Compartiment.REGISTRU_FAPTE, Compartiment.CATALOG_OFERTE, Compartiment.PROFIL_BRAND):
        assert c not in automate


def test_continutul_se_valideaza_cu_schema_compartimentului_si_are_o_limita() -> None:
    class Proba(BaseModel):
        titlu: str

    inregistreaza_schema(Compartiment.IDENTITATE_VIZUALA, Proba)
    try:
        assert valideaza_continut(Compartiment.IDENTITATE_VIZUALA, {"titlu": "x"}) == {"titlu": "x"}
        try:
            valideaza_continut(Compartiment.IDENTITATE_VIZUALA, {"altceva": 1})
        except ContinutInvalid:
            pass
        else:
            raise AssertionError("schema nu a fost aplicată")
    finally:
        _SCHEME.pop(Compartiment.IDENTITATE_VIZUALA, None)
    try:
        valideaza_continut(Compartiment.PLAYBOOK, {"text": "a" * 50_000})
    except ContinutInvalid:
        pass
    else:
        raise AssertionError("limita de mărime nu a fost aplicată")


def test_textul_de_cautare_e_determinist() -> None:
    c = {"b": ["doi", {"x": "trei"}], "a": "unu", "n": 7, "f": True}
    assert text_de_cautare(c) == "unu doi trei 7" or text_de_cautare(c) == "unu 7 doi trei"
    assert text_de_cautare(c) == text_de_cautare(dict(reversed(list(c.items()))))


def test_diferenta_arata_ce_s_a_adaugat_scos_si_schimbat() -> None:
    a = {"pret": {"valoare": 100, "moneda": "RON"}, "taguri": ["x", "y"], "vechi": 1}
    b = {"pret": {"valoare": 120, "moneda": "RON"}, "taguri": ["x"], "nou": "da"}
    assert diferenta(a, b) == [
        Schimbare("nou", Fel.ADAUGAT, None, "da"),
        Schimbare("pret.valoare", Fel.SCHIMBAT, 100, 120),
        Schimbare("taguri.1", Fel.SCOS, "y", None),
        Schimbare("vechi", Fel.SCOS, 1, None),
    ]
    assert diferenta(a, a) == []
    # 1 și True sunt valori diferite (nu „egale” în Python)
    assert diferenta({"v": 1}, {"v": True}) == [Schimbare("v", Fel.SCHIMBAT, 1, True)]
