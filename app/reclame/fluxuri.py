"""Joburile reclamelor (F13): citirea orară a rezultatelor."""

import datetime as dt
from typing import Any

from app.operare import motor
from app.reclame import rezultate

NUME_CITIRE = "reclame.citire"


@motor.pas("reclame.pas_citire")
def _pas_citire() -> str:
    return str(rezultate.citeste_toate())


@motor.flux(NUME_CITIRE)
def flux_citire(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas_citire()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME_CITIRE, "17 * * * *", flux_citire)


declara_programari()
