"""Joburile programate ale producției (rulează în procesul `worker`, la minut): întrerupătorul global (F2.4).

Fluxul programat e mic și deschide el însuși o sesiune de agenție (fără utilizator: un proces de sistem, ca
watchdog-ul), fiindcă evaluarea citește rezultatele tuturor clienților.
"""

import datetime as dt
from typing import Any

from app.db import sesiune_agentie
from app.operare import motor
from app.productie import intrerupator

NUME_TIC = "productie.tic"


@motor.pas(nume="productie.pas_intrerupator")
def _evalueaza_intrerupatorul() -> str:
    with sesiune_agentie() as db:
        e = intrerupator.evalueaza(db)
    return "declansat" if e.declansat_acum else ("oprit" if e.oprit else "ok")


@motor.flux(NUME_TIC)
def tic(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    """Un tic pe minut: evaluează întrerupătorul. (Aprobările restante se adaugă aici în F2.8.)"""
    return _evalueaza_intrerupatorul()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME_TIC, "* * * * *", tic)


declara_programari()
