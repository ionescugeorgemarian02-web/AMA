"""Ce primește un validator: conținutul de validat, livrabilul și accesul (opțional) la bază, ca date
pregătite.

Validatorii deterministe (V0–V2) sunt funcții pure peste `text` / `campuri`; ce depinde de client (faptele
aprobate, ghidul de brand, sursele colectate, regulile clientului) se citește prin `intrare.memo(...)`, o
dată pe
rulare, prin API-urile modulelor respective (nu prin SQL direct).
"""

import datetime as dt
import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from sqlalchemy.orm import Session

T = TypeVar("T")


def amprenta_text(text: str, campuri: dict[str, Any] | None = None) -> str:
    """Amprenta SHA-256 a conținutului validat (textul și câmpurile, în ordine stabilă)."""
    import json

    return hashlib.sha256(
        (text + "\x1f" + json.dumps(campuri or {}, sort_keys=True, ensure_ascii=False)).encode()
    ).hexdigest()


@dataclass(frozen=True)
class Continut:
    """O versiune de conținut a livrabilului (vezi `continut.py`)."""

    versiune: int
    text: str
    campuri: dict[str, Any] = field(default_factory=dict)
    active: tuple[dict[str, Any], ...] = ()
    autor: str = ""
    model_autor: str | None = None

    @property
    def amprenta(self) -> str:
        return amprenta_text(self.text, self.campuri)

    def texte(self) -> list[tuple[str, str]]:
        """Bucățile de text ale conținutului, ca (nume câmp, text): corpul și câmpurile text de pe canal."""
        iesire = [("text", self.text)] if self.text.strip() else []
        for nume in sorted(self.campuri):
            val = self.campuri[nume]
            if isinstance(val, str) and val.strip():
                iesire.append((nume, val))
            elif isinstance(val, list) and all(isinstance(x, str) for x in val):
                iesire.extend((f"{nume}[{i}]", x) for i, x in enumerate(val) if x.strip())
        return iesire

    @property
    def text_complet(self) -> str:
        return "\n".join(t for _, t in self.texte())


@dataclass(frozen=True)
class SituatieLivrabil:
    id: uuid.UUID
    tenant_id: uuid.UUID
    tip: str
    canal: str
    versiune: int
    runda: int
    clasa_actiune: str = "publicare_continut"


@dataclass
class Intrare:
    livrabil: SituatieLivrabil
    continut: Continut
    la: dt.datetime  # data publicării / a validării: faptele se citesc valabile la ea
    db: Session | None = None
    judecatori: bool = False  # treptele V3 rulează?
    v4: bool = False  # treapta V4 rulează?
    _memo: dict[str, Any] = field(default_factory=dict)

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.livrabil.tenant_id

    @property
    def text(self) -> str:
        return self.continut.text_complet

    def memo(self, cheie: str, f: Callable[[], T]) -> T:
        """Valoarea citită o singură dată pe rulare (faptele, ghidul etc. nu se recitesc)."""
        if cheie not in self._memo:
            self._memo[cheie] = f()
        return self._memo[cheie]  # type: ignore[no-any-return]

    def baza(self) -> Session:
        if self.db is None:
            raise RuntimeError("validatorul cere acces la bază, iar intrarea nu are sesiune")
        return self.db
