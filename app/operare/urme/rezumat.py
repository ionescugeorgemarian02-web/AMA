"""Rezumatul intrărilor și ieșirilor unei urme: fără secrete, fără date personale în clar, mărginit (FT.1)."""

import datetime as dt
import re
import uuid
from decimal import Decimal
from enum import Enum
from typing import Any

PARTI_SECRETE = (
    "parola", "password", "secret", "token", "jeton", "totp", "hash", "cheie", "key",
    "authorization", "cookie", "csrf", "otp",
)  # fmt: skip
ASCUNS = "[ascuns]"
TEXT_MAXIM = 200
LISTA_MAXIMA = 20
ADANCIME_MAXIMA = 4

TIPARE: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[email]"),
    (re.compile(r"\bRO\d{2}[A-Z]{4}[A-Z0-9]{16}\b", re.IGNORECASE), "[iban]"),
    (re.compile(r"\b[1-8]\d{12}\b"), "[cnp]"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[card]"),
    (re.compile(r"(?:\+?40|\b0)[ .-]?7\d{2}[ .-]?\d{3}[ .-]?\d{3}\b"), "[telefon]"),
    (re.compile(r"\b(?:Bearer|Basic)\s+\S+", re.IGNORECASE), "[ascuns]"),
)


def mascheaza(text: str) -> str:
    for tipar, inlocuire in TIPARE:
        text = tipar.sub(inlocuire, text)
    return text


def _secret(cheie: object) -> bool:
    k = str(cheie).lower()
    return any(p in k for p in PARTI_SECRETE)


def rezuma(valoare: Any, _adancime: int = 0) -> Any:
    """O formă JSON scurtă și sigură a oricărei valori (dict, listă, text, număr, UUID, dată, enum)."""
    if valoare is None or isinstance(valoare, bool | int):
        return valoare
    if isinstance(valoare, float | Decimal):
        return float(valoare)
    if isinstance(valoare, Enum):
        return rezuma(valoare.value, _adancime)
    if isinstance(valoare, uuid.UUID):
        return str(valoare)
    if isinstance(valoare, dt.datetime | dt.date):
        return valoare.isoformat()
    if _adancime >= ADANCIME_MAXIMA:
        return "[…]"
    if isinstance(valoare, dict):
        out: dict[str, Any] = {}
        for i, (k, v) in enumerate(valoare.items()):
            if i >= LISTA_MAXIMA:
                out["…"] = f"încă {len(valoare) - LISTA_MAXIMA}"
                break
            out[str(k)[:60]] = ASCUNS if _secret(k) else rezuma(v, _adancime + 1)
        return out
    if isinstance(valoare, list | tuple | set | frozenset):
        elemente = list(valoare)
        rez = [rezuma(v, _adancime + 1) for v in elemente[:LISTA_MAXIMA]]
        if len(elemente) > LISTA_MAXIMA:
            rez.append(f"… încă {len(elemente) - LISTA_MAXIMA}")
        return rez
    text = mascheaza(str(valoare))
    return text if len(text) <= TEXT_MAXIM else text[: TEXT_MAXIM - 1] + "…"


def rezuma_dict(valoare: dict[str, Any] | None) -> dict[str, Any]:
    r = rezuma(valoare or {})
    return r if isinstance(r, dict) else {"valoare": r}
