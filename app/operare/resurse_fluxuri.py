"""Ticul de resurse (F15.1, docs/25 §25.3): la 5 minute, discul și memoria, cu curățare și alertă."""

import datetime as dt
from typing import Any

from app.operare import motor, resurse
from app.operare.motor import Coada

NUME = "operare.resurse"


@motor.pas(nume="operare.resurse_pas")
def _verifica() -> str:
    r = resurse.verifica()
    return f"disc {r['disc_pct']:.0f}% memorie {r['memorie_pct']:.0f}% sterse {r['sterse']}"


@motor.flux(NUME)
def tic_resurse(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _verifica()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME, "*/5 * * * *", tic_resurse, coada=Coada.URGENT)


declara_programari()
