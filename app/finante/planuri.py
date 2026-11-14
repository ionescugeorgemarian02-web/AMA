"""Planurile agenției (docs/04, docs/19 §19.1 „Servicii și pachete”, „Prețuri”). Nucleu pur: date, fără bază.

Prețurile și cantitățile sunt [I] (ipoteze de pornire, în lei, fără TVA): se confirmă la lansare (F15).
Aceleași date alimentează site-ul (paginile Servicii și Prețuri), facturarea (F7.6) și raportul lunar (F7.8:
livrat față de pachet)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    cod: str
    nume: str
    pret_lunar: int  # lei, fără TVA [I]
    pentru: str
    livrabile: dict[str, int]  # tip de livrabil -> număr pe lună [I]
    canale: int
    nu_include: tuple[str, ...]


SETUP = 990  # lei, o singură dată: onboarding, Creierul de brand, strategia pe 90 de zile [I]
ETICHETE_LIVRABILE = {
    "postare": "postări",
    "video": "videoclipuri scurte",
    "articol": "articole de blog",
    "raport": "raport lunar",
}
PLANURI: dict[str, Plan] = {
    p.cod: p
    for p in (
        Plan(
            "start",
            "Start",
            1490,
            "firme mici care vor prezență constantă pe 2 canale",
            {"postare": 12, "video": 2, "articol": 0, "raport": 1},
            2,
            ("reclame plătite", "răspunsuri în inbox", "fotografii la fața locului"),
        ),
        Plan(
            "crestere",
            "Creștere",
            2990,
            "firme care vor clienți noi din conținut și din căutări",
            {"postare": 20, "video": 4, "articol": 2, "raport": 1},
            3,
            ("bugetul de reclame", "fotografii la fața locului"),
        ),
        Plan(
            "pro",
            "Pro",
            5490,
            "firme cu buget de reclame și mai multe canale",
            {"postare": 30, "video": 8, "articol": 4, "raport": 1},
            4,
            ("bugetul de reclame (se plătește direct platformei)",),
        ),
    )
}


def plan(cod: str) -> Plan:
    try:
        return PLANURI[cod]
    except KeyError:
        raise ValueError(f"plan necunoscut: {cod}") from None
