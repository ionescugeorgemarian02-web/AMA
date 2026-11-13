"""F5.9 — nucleul pur al biroului de aprobări: ordinea (urgență, termen, prioritate, slot), diferența și motivele."""

import datetime as dt

from app.productie.reguli_aprobare import MOTIVE_RESPINGERE
from app.validare import birou_nucleu as n

ACUM = dt.datetime(2026, 11, 13, 9, tzinfo=dt.UTC)


def h(ore: float) -> dt.datetime:
    return ACUM + dt.timedelta(hours=ore)


def test_ordinea_urgente_apoi_termen_prioritate_si_slot() -> None:
    cereri = [
        n.Cheie("postare-tarziu", h(30), "postare"),
        n.Cheie("reclama-tarziu", h(30), "reclama_text"),
        n.Cheie("postare-urgenta", h(1), "postare"),
        n.Cheie("email-curand", h(5), "email"),
        n.Cheie("postare-slot", h(30), "postare", slot_la=h(40)),
    ]
    assert n.ordoneaza(cereri, ACUM) == [
        "postare-urgenta",
        "email-curand",
        "reclama-tarziu",
        "postare-slot",
        "postare-tarziu",
    ]
    assert n.ordoneaza(list(reversed(cereri)), ACUM) == n.ordoneaza(cereri, ACUM)


def test_diferenta_pe_cuvinte() -> None:
    d = n.diferenta("Cafea proaspătă la 49 lei azi.", "Cafea proaspătă la 45 lei mâine.")
    assert [(b.tip, b.text) for b in d] == [
        ("egal", "Cafea proaspătă la"),
        ("scos", "49"),
        ("adaugat", "45"),
        ("egal", "lei"),
        ("scos", "azi."),
        ("adaugat", "mâine."),
    ]
    assert n.diferenta("la fel", "la fel") == [n.Bucata("egal", "la fel")]


def test_statistica_motivelor() -> None:
    s = n.statistica_motive(["hook_slab", "prea_lung", "hook_slab", None, "inventat"], MOTIVE_RESPINGERE)
    assert s[:2] == [("altceva", "Altceva", 2), ("hook_slab", "Hook slab", 2)]  # la egalitate, după cod
    assert ("altceva", "Altceva", 2) in s and ("prea_lung", "Prea lung", 1) in s
