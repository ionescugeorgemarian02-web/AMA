"""Ceasul și pauzele gateway-ului, înlocuibile în teste (fără `sleep` real, fără așteptat minute)."""

import datetime as dt
import time
from collections.abc import Callable

_ceas: Callable[[], dt.datetime] | None = None
_dormi: Callable[[float], None] | None = None


def acum() -> dt.datetime:
    return _ceas() if _ceas else dt.datetime.now(dt.UTC)


def dormi(secunde: float) -> None:
    """Pauza scurtă dintre reîncercările pe același furnizor (7.5). Nu e amânare: amânarea e durabilă
    (motor)."""
    (_dormi or time.sleep)(secunde)


def seteaza_ceas(f: Callable[[], dt.datetime] | None) -> None:
    global _ceas
    _ceas = f


def seteaza_dormi(f: Callable[[float], None] | None) -> None:
    global _dormi
    _dormi = f
