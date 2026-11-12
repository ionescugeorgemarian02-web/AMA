"""Joburile programate ale producției (rulează în procesul `worker`, la minut): întrerupătorul global (F2.4)
și expirarea / reamintirea cererilor de aprobare (F2.8).

Fluxul programat e mic și deschide el însuși o sesiune de agenție (fără utilizator: un proces de sistem, ca
watchdog-ul), fiindcă citește rezultatele și termenele tuturor clienților.
"""

import datetime as dt
from typing import Any

from app.db import sesiune_agentie
from app.operare import motor
from app.productie import aprobari, intrerupator

NUME_TIC = "productie.tic"


@motor.pas(nume="productie.pas_intrerupator")
def _evalueaza_intrerupatorul() -> str:
    with sesiune_agentie() as db:
        e = intrerupator.evalueaza(db)
    return "declansat" if e.declansat_acum else ("oprit" if e.oprit else "ok")


@motor.pas(nume="productie.pas_aprobari")
def _aprobari_restante() -> str:
    """Cererile cu termenul trecut expiră (nu se aprobă); cele aproape de termen primesc o reamintire."""
    with sesiune_agentie() as db:
        expirate = aprobari.expira_restante(db)
        reamintite = aprobari.trimite_reamintiri(db)
    return f"expirate={len(expirate)} reamintite={len(reamintite)}"


@motor.flux(NUME_TIC)
def tic(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    """Un tic pe minut: aprobările restante și întrerupătorul global. Pașii sunt independenți: dacă unul
    aruncă, jobul eșuează și intră în coada de erori (F2.7), iar la următorul tic se reia totul."""
    return f"{_aprobari_restante()} intrerupator={_evalueaza_intrerupatorul()}"


def declara_programari() -> None:
    motor.programeaza_recurent(NUME_TIC, "* * * * *", tic)


declara_programari()
