"""Joburile planificatorului de capacitate: zilnic (04:55, ora României, înainte de ziua de lucru) și la
cerere."""

import datetime as dt
from typing import Any

from app.operare import motor
from app.operare.motor import Coada, Prioritate
from app.planificare import capacitate

NUME_ZILNIC = "planificare.capacitate_zilnica"
NUME_LA_CERERE = "planificare.capacitate_la_cerere"


@motor.pas(nume="planificare.pas_capacitate")
def _planifica() -> str:
    plan = capacitate.planifica()
    return (
        f"livrabile={len(plan.rezultat.verdicte)} amanate={len(plan.amanate)} protejate={len(plan.protejate)}"
    )


@motor.flux(NUME_ZILNIC)
def capacitate_zilnica(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _planifica()


@motor.flux(NUME_LA_CERERE)
def capacitate_la_cerere(motiv: str) -> str:
    return _planifica()


def planifica_la_cerere() -> str:
    """Pune planul în coadă acum (același rezultat ca la rularea zilnică). Întoarce identificatorul
    jobului."""
    acum = dt.datetime.now(dt.UTC)
    return motor.trimite(
        capacitate_la_cerere,
        "cerere",
        coada=Coada.IO,
        prioritate=Prioritate.P1,
        cheie=f"capacitate:{acum:%Y%m%d%H%M}",
    )


def declara_programari() -> None:
    motor.programeaza_recurent(NUME_ZILNIC, "55 4 * * *", capacitate_zilnica, coada=Coada.IO)


declara_programari()
