"""Planificarea (A4, tip D): planificatorul de capacitate (F3.11). Restul aplicației folosește doar ce se
exportă aici:

    from app import planificare

    plan = planificare.planifica()              # acum: citește, decide, amână, scrie, anunță
    job = planificare.planifica_la_cerere()     # același lucru, ca job în coadă
"""

from app.planificare.capacitate import Plan, planifica, sfarsit_zi
from app.planificare.reguli import Capacitate, Cost, Decizie, Element, Rezultat, Verdict


def planifica_la_cerere() -> str:
    from app.planificare import fluxuri

    return fluxuri.planifica_la_cerere()


__all__ = [
    "Capacitate",
    "Cost",
    "Decizie",
    "Element",
    "Plan",
    "Rezultat",
    "Verdict",
    "planifica",
    "planifica_la_cerere",
    "sfarsit_zi",
]
