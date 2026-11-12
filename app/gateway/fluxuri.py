"""Joburile programate ale gateway-ului: curățarea zilnică a contoarelor vechi și a conținutului expirat
(20.4)."""

import datetime as dt
from typing import Any

from app.gateway import bugete, jurnal, limitator
from app.operare import motor

NUME_CURATARE = "gateway.curatare"


@motor.pas(nume="gateway.pas_curatare")
def _curata() -> str:
    contoare = limitator.curata()
    continut = jurnal.curata_continut()
    consum = bugete.curata_vechi()
    return f"contoare={contoare} continut={continut} consum={consum}"


@motor.flux(NUME_CURATARE)
def curatare(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    """O dată pe zi (03:17, ora României): contoarele și blocajele de peste 3 zile, conținutul apelurilor
    peste 30 de zile."""
    return _curata()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME_CURATARE, "17 3 * * *", curatare)


declara_programari()
