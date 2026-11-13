"""Autorul reparațiilor: un punct de extensie. Autorii de text (E1–E6) apar în F6 și se înregistrează aici.

Bucla de reparație (`ciclu.ruleaza_repararea`) cheamă autorul înregistrat cu instrucțiunea unificată a
validatorilor;
autorul întoarce conținutul corectat. Autorul nu validează nimic și nu mută starea: o face ciclul.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.validare.intrare import Continut


@dataclass(frozen=True)
class SarcinaReparatie:
    livrabil_id: uuid.UUID
    tenant_id: uuid.UUID
    tip: str
    canal: str
    versiune: int
    runda: int  # a câta reparație (1 sau 2)
    continut: Continut
    instructiune: str  # mesajul unic cu corecturile tuturor validatorilor


@dataclass(frozen=True)
class ContinutNou:
    text: str
    campuri: dict[str, Any] = field(default_factory=dict)
    active: list[dict[str, Any]] = field(default_factory=list)
    autor: str = "E?"
    model_autor: str | None = None  # `furnizor/identificator`: judecătorii folosesc ALT model


Autor = Callable[[Session, SarcinaReparatie], ContinutNou | None]

_autor: Autor | None = None
# Surse de autori (F6): fiecare întoarce conținutul corectat pentru livrabilele ei și `None` pentru celelalte.
# Un autor
# înregistrat explicit cu `inregistreaza` (testele F5) are întâietate.
_surse: list[Autor] = []


def inregistreaza(f: Autor | None) -> None:
    global _autor
    _autor = f


def inregistreaza_sursa(f: Autor) -> None:
    """Adaugă o sursă de autori (o singură dată pe funcție)."""
    if f not in _surse:
        _surse.append(f)


def _din_surse(db: Session, sarcina: SarcinaReparatie) -> ContinutNou | None:
    for f in _surse:
        nou = f(db, sarcina)
        if nou is not None:
            return nou
    return None


def curent() -> Autor | None:
    """Autorul de chemat: cel explicit, altfel sursele (care pot întoarce `None`: livrabilul nu e al
    nimănui)."""
    if _autor is not None:
        return _autor
    return _din_surse if _surse else None
