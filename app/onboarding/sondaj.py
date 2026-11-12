"""Eșantionul determinist al verificării prin sondaj (F4.10) — nucleu pur.

Din lista trimiterilor unui brief se alege un eșantion care depinde DOAR de trimiteri și de o sămânță
(de obicei
amprenta conținutului): aceeași intrare dă același eșantion, deci verificarea e reproductibilă și nu
poate fi „norocoasă”
la a doua rulare. Mărimea: `max(minim, ceil(fractie · n))`, plafonată la `n`. Ordinea: după
SHA-256(sămânță + trimitere).
"""

import hashlib
import math


def esantion(trimiteri: list[str], *, samanta: str, fractie: float = 0.3, minim: int = 5) -> list[str]:
    unice = sorted(set(trimiteri))
    if not unice:
        return []
    n = min(len(unice), max(minim, math.ceil(fractie * len(unice))))
    ordonate = sorted(unice, key=lambda t: hashlib.sha256(f"{samanta}\x1f{t}".encode()).hexdigest())
    return sorted(ordonate[:n])
