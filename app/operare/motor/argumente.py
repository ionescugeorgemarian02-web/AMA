"""Regula argumentelor: fluxurile și pașii primesc doar identificatori, nu conținut și nu secrete.

Argumentele și rezultatele pașilor se serializează în tabelele bibliotecii (schema `dbos`), care nu au izolare
pe client și se citesc cu rolul aplicației. De aceea la intrare se acceptă doar valori mici și simple:
identificatori (UUID, texte scurte), numere, momente, enumerări și liste scurte de astfel de valori.
Textul unui articol, o pagină descărcată, o cheie de API sau o parolă nu au ce căuta aici: se țin în tabelele
de business (cu RLS) sau în depozitul de secrete, iar fluxul primește identificatorul lor.
"""

import datetime as dt
import enum
import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from app.operare.motor.erori import ArgumentNepermis

LUNGIME_MAXIMA_TEXT = 200
ELEMENTE_MAXIME = 64

_SCALARI = (bool, int, float, uuid.UUID, dt.datetime, dt.date)


def _scalar(valoare: object, cale: str) -> None:
    if valoare is None or isinstance(valoare, _SCALARI):
        return
    if isinstance(valoare, enum.Enum):
        _scalar(valoare.value, cale)
        return
    if isinstance(valoare, str):
        if len(valoare) > LUNGIME_MAXIMA_TEXT:
            raise ArgumentNepermis(
                f"{cale}: text de {len(valoare)} caractere (maxim {LUNGIME_MAXIMA_TEXT}); "
                "pasează identificatorul conținutului, nu conținutul"
            )
        return
    raise ArgumentNepermis(
        f"{cale}: tip nepermis {type(valoare).__name__}; doar identificatori și valori simple"
    )


def verifica_valoare(valoare: Any, cale: str = "arg") -> None:
    """Scalar, listă plată de scalari sau dicționar plat cu chei text și valori scalare."""
    if isinstance(valoare, Mapping):
        if len(valoare) > ELEMENTE_MAXIME:
            raise ArgumentNepermis(f"{cale}: prea multe chei ({len(valoare)})")
        for k, v in valoare.items():
            if not isinstance(k, str):
                raise ArgumentNepermis(f"{cale}: cheile dicționarului trebuie să fie text")
            _scalar(v, f"{cale}[{k!r}]")
        return
    if isinstance(valoare, list | tuple):
        if len(valoare) > ELEMENTE_MAXIME:
            raise ArgumentNepermis(f"{cale}: prea multe elemente ({len(valoare)})")
        for i, v in enumerate(valoare):
            _scalar(v, f"{cale}[{i}]")
        return
    _scalar(valoare, cale)


def verifica(nume: str, args: Iterable[Any], kwargs: Mapping[str, Any]) -> None:
    """Aruncă `ArgumentNepermis` dacă vreun argument nu e identificator/valoare simplă."""
    for i, a in enumerate(args):
        verifica_valoare(a, f"{nume}(arg {i})")
    for k, v in kwargs.items():
        verifica_valoare(v, f"{nume}({k}=)")
