"""Raportul săptămânal al pilotului (F15.5): luni dimineața, pentru săptămâna încheiată, cu anunț."""

import datetime as dt
from typing import Any

from app.db import sesiune_agentie
from app.lansare import pilot
from app.operare import motor, notificari

NUME = "lansare.pilot_saptamanal"


@motor.pas(nume="lansare.pilot_saptamanal_pas")
def _raport(saptamana_iso: str) -> int:
    with sesiune_agentie() as db:
        r = pilot.raport_saptamanal(db, dt.date.fromisoformat(saptamana_iso))
    if r:
        lipsa = sum(1 for x in r if x["feedback_lipsa"])
        incidente = sum(int(x["incidente_critice"]) for x in r)
        notificari.notifica(
            notificari.Nivel.CRITIC if incidente else notificari.Nivel.INFORMATIV,
            "Raportul săptămânal al pilotului",
            f"{len(r)} clienți; incidente critice: {incidente}; feedback lipsă: {lipsa}.",
            url="/lansare/pilot",
        )
    return len(r)


@motor.flux(NUME)
def tic_pilot(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    saptamana = pilot.luni(moment.date()) - dt.timedelta(days=7)
    return str(_raport(saptamana.isoformat()))


def declara_programari() -> None:
    motor.programeaza_recurent(NUME, "37 7 * * 1", tic_pilot)


declara_programari()
