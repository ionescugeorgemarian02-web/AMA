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


Autor = Callable[[Session, SarcinaReparatie], ContinutNou]

_autor: Autor | None = None


def inregistreaza(f: Autor | None) -> None:
    global _autor
    _autor = f


def curent() -> Autor | None:
    return _autor
