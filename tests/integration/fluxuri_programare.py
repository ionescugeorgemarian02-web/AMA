"""Fluxuri de probă pentru planificator (F2.6), rulate în procesul testului."""

import datetime as dt
import threading
import time
from typing import Any

from app.operare import motor

_lock = threading.Lock()
TICURI: list[tuple[dt.datetime, float, dict[str, Any] | None]] = []  # (tic programat, primit la, context)
SLOTURI: dict[str, float] = {}  # cheie -> ora (monotonică) la care a pornit


def reseteaza() -> None:
    with _lock:
        TICURI.clear()
        SLOTURI.clear()


def ticuri() -> list[dt.datetime]:
    with _lock:
        return [t[0] for t in TICURI]


@motor.flux("programare.tic")
def tic(moment: dt.datetime, context: dict[str, Any] | None) -> None:
    with _lock:
        TICURI.append((moment, time.monotonic(), context))


@motor.flux("programare.slot")
def slot(cheie: str) -> str:
    with _lock:
        SLOTURI[cheie] = time.monotonic()
    return cheie
