"""Diferența dintre două versiuni ale conținutului unei intrări (F4.1). Funcții pure, deterministe."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Fel(StrEnum):
    ADAUGAT = "adaugat"
    SCOS = "scos"
    SCHIMBAT = "schimbat"


@dataclass(frozen=True)
class Schimbare:
    """O modificare la o cale din JSON (`pret.valoare`, `ton.0`)."""

    cale: str
    fel: Fel
    inainte: Any = None
    dupa: Any = None


def diferenta(a: Any, b: Any, _cale: str = "") -> list[Schimbare]:
    """Schimbările de la `a` la `b`, ordonate după cale. Obiectele se compară cheie cu cheie, listele pe
    poziție (o listă schimbată se vede element cu element)."""
    if isinstance(a, dict) and isinstance(b, dict):
        iesire: list[Schimbare] = []
        for k in sorted(set(a) | set(b)):
            cale = f"{_cale}.{k}" if _cale else str(k)
            if k not in a:
                iesire.append(Schimbare(cale, Fel.ADAUGAT, None, b[k]))
            elif k not in b:
                iesire.append(Schimbare(cale, Fel.SCOS, a[k], None))
            else:
                iesire.extend(diferenta(a[k], b[k], cale))
        return iesire
    if isinstance(a, list) and isinstance(b, list):
        iesire = []
        for i in range(max(len(a), len(b))):
            cale = f"{_cale}.{i}" if _cale else str(i)
            if i >= len(a):
                iesire.append(Schimbare(cale, Fel.ADAUGAT, None, b[i]))
            elif i >= len(b):
                iesire.append(Schimbare(cale, Fel.SCOS, a[i], None))
            else:
                iesire.extend(diferenta(a[i], b[i], cale))
        return iesire
    if a == b and type(a) is type(b):
        return []
    return [Schimbare(_cale, Fel.SCHIMBAT, a, b)]
