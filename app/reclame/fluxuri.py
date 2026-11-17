"""Joburile reclamelor (F13): citirea orară a rezultatelor."""

import datetime as dt
from typing import Any

from app.operare import motor
from app.reclame import rezultate, strateg, teste, urgenta

NUME_CITIRE = "reclame.citire"
NUME_STRATEG = "reclame.strateg"


@motor.pas("reclame.pas_citire")
def _pas_citire() -> str:
    citite = rezultate.citeste_toate()
    anomalii = urgenta.supravegheaza()  # F13.5: după fiecare citire, semnalele de urgență
    testele = teste.evalueaza_toate()  # F13.9: testele de creative, pe cifrele proaspete
    return f"{citite} anomalii={len(anomalii)} teste={testele}"


@motor.flux(NUME_CITIRE)
def flux_citire(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas_citire()


@motor.pas("reclame.pas_strateg")
def _pas_strateg() -> str:
    return str(strateg.revizuieste())


@motor.flux(NUME_STRATEG)
def flux_strateg(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas_strateg()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME_CITIRE, "17 * * * *", flux_citire)
    motor.programeaza_recurent(NUME_STRATEG, "41 6 * * 1", flux_strateg)  # luni dimineață (16.9)


declara_programari()
