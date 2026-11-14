"""Contractul conectorilor de efecte externe (F2.5, 7.3): ce cere executorul de la o platformă.

Un conector știe doar să (1) trimită un efect și (2) spună dacă un efect există deja la platformă. Nu decide
nimic: oprirea, idempotența, reîncercările și starea livrabilului sunt ale executorului
(`app.operare.efecte`).
Conectorul este chemat DOAR de executor (garda `scripts/check_efecte.py`).

Erorile se aruncă din `app.operare.motor` (clasificarea din 7.5):
- `EroareTemporara` (rețea, limită de rată, eroare de server, timeout): rezultatul poate fi necunoscut;
  executorul
  întreabă `verifica` înainte de orice reîncercare;
- `EroareAutentificare`: tokenul a expirat; canalul se pune pe pauză și se cere reautorizare;
- `EroareDefinitiva`: platforma a refuzat; nu are sens reîncercarea.

Tokenurile NU intră în `EfectDeTrimis`: conectorul le rezolvă el însuși, la execuție (din depozitul de
secrete).
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class EfectDeTrimis:
    """Ce primește conectorul. `idem` este cheia de idempotență (client:livrabil:canal:versiune:tip):
    platformele
    care o acceptă o primesc ca atare, iar `verifica` o folosește ca să găsească efectul."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    livrabil_id: uuid.UUID
    canal: str
    versiune: int
    tip: str
    idem: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RezultatPlatforma:
    """Ce a întors platforma: identificatorul și linkul efectului (postarea publicată)."""

    id_extern: str
    link: str = ""


@runtime_checkable
class Conector(Protocol):
    def trimite(self, efect: EfectDeTrimis) -> RezultatPlatforma: ...

    def verifica(self, efect: EfectDeTrimis) -> RezultatPlatforma | None:
        """Efectul există deja la platformă? Întoarce rezultatul lui, sau `None` dacă nu există."""
        ...


@dataclass(frozen=True)
class EfectSistem:
    """Un efect extern care nu ține de un livrabil (F7): un email tranzacțional, un apel la procesatorul de
    plăți.
    `idem` e cheia de idempotență a efectului; `payload` nu poartă secrete (cheile se rezolvă în conector)."""

    id: uuid.UUID
    tip: str
    idem: str
    tenant_id: uuid.UUID | None
    payload: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ConectorSistem(Protocol):
    def trimite(self, efect: EfectSistem) -> RezultatPlatforma: ...
