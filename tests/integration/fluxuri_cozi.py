"""Fluxuri de probă pentru testele cozilor, rulate în procesul testului (executor în proces).

Un job „pornește” când intră în corpul lui și „așteaptă” un eveniment de eliberare pus de test. Ordinea pornirilor
și momentele se țin în memorie; testele nu depind de pauze, ci de aceste evenimente.
"""

import threading
import time

from app.operare import motor

_lock = threading.Lock()
PORNITE: list[str] = []
MOMENTE: dict[str, float] = {}
_pornit: dict[str, threading.Event] = {}
_elibereaza: dict[str, threading.Event] = {}
_blocheaza: set[str] = set()


def reseteaza() -> None:
    elibereaza_tot()
    with _lock:
        PORNITE.clear()
        MOMENTE.clear()
        _pornit.clear()
        _elibereaza.clear()
        _blocheaza.clear()


def blocheaza(*nume: str) -> None:
    """Joburile cu aceste nume stau după pornire până la `elibereaza(nume)`."""
    with _lock:
        for n in nume:
            _blocheaza.add(n)
            _elibereaza.setdefault(n, threading.Event())


def elibereaza(*nume: str) -> None:
    with _lock:
        for n in nume:
            _elibereaza.setdefault(n, threading.Event()).set()


def elibereaza_tot() -> None:
    with _lock:
        for e in _elibereaza.values():
            e.set()


def a_pornit(nume: str) -> bool:
    with _lock:
        return nume in PORNITE


def asteapta_pornirea(nume: str, timeout_sec: float = 10.0) -> None:
    with _lock:
        e = _pornit.setdefault(nume, threading.Event())
    if not e.wait(timeout_sec):
        raise AssertionError(f"jobul {nume} nu a pornit în {timeout_sec} s (pornite: {PORNITE})")


def pornite() -> list[str]:
    with _lock:
        return list(PORNITE)


@motor.flux("cozi.job")
def job(nume: str) -> str:
    with _lock:
        PORNITE.append(nume)
        MOMENTE[nume] = time.monotonic()
        _pornit.setdefault(nume, threading.Event()).set()
        eveniment = _elibereaza.get(nume) if nume in _blocheaza else None
    if eveniment is not None:
        eveniment.wait(60)
    return nume
