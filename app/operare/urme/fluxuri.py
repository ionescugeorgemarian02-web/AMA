"""Jobul lunar al urmelor (FT.4): pe 1 ale lunii, analiza lunii încheiate."""

import datetime as dt
from typing import Any

from app.db import sesiune_agentie
from app.operare import motor
from app.operare.urme import analiza

NUME_ANALIZA = "urme.analiza_lunara"


@motor.pas("urme.pas_analiza")
def _pas_analiza(luna_iso: str) -> str:
    with sesiune_agentie() as db:
        r = analiza.genereaza(db, dt.date.fromisoformat(luna_iso))
    return f"{luna_iso}: {r['total_urme']} urme, {r['total_esecuri']} eșecuri, {len(r['regresii'])} regresii"


@motor.flux(NUME_ANALIZA)
def flux_analiza(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas_analiza(analiza.luna_precedenta(analiza.luna_de(moment)).isoformat())


def declara_programari() -> None:
    motor.programeaza_recurent(NUME_ANALIZA, "23 4 1 * *", flux_analiza)  # 1 ale lunii, 04:23 (ora afacerii)


declara_programari()
