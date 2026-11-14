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

import datetime as dt
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
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


# --- tipurile publicării prin API (F9.1): doar date, importabile de oriunde
# -------------------------------------


class StarePostare(StrEnum):
    PUBLICATA = "publicata"  # vizibilă public
    PRIVATA = "privata"  # există, dar doar contul o vede (YouTube înainte de audit, TikTok neauditat)
    CIORNA = "ciorna"  # trimisă în aplicația platformei; omul o publică de acolo (TikTok)
    IN_PROCESARE = "in_procesare"  # platforma încă o procesează
    ESUATA = "esuata"  # platforma a respins-o după primire
    INEXISTENTA = "inexistenta"  # ștearsă sau negăsită (15.8: devine incident)


ETICHETE_STARE: dict[StarePostare, str] = {
    StarePostare.PUBLICATA: "Publică",
    StarePostare.PRIVATA: "Privată (până la audit)",
    StarePostare.CIORNA: "Ciornă în aplicație",
    StarePostare.IN_PROCESARE: "În procesare",
    StarePostare.ESUATA: "Respinsă de platformă",
    StarePostare.INEXISTENTA: "Ștearsă sau negăsită",
}


@dataclass(frozen=True)
class Token:
    """Accesul unui cont la o platformă. Valorile secrete nu apar în `repr` (jurnale, erori)."""

    acces: str = field(repr=False)
    expira_la: dt.datetime | None = None
    reimprospatare: str = field(default="", repr=False)
    cont_extern: str = ""  # id-ul paginii / contului / canalului la platformă
    scopuri: tuple[str, ...] = ()

    def expirat(self, acum: dt.datetime | None = None) -> bool:
        acum = acum or dt.datetime.now(dt.UTC)
        return self.expira_la is not None and self.expira_la <= acum


@dataclass(frozen=True)
class Limite:
    """Limitele citite de la platformă (endpoint sau antete). `sursa` spune de unde; `None` = platforma nu
    spune."""

    sursa: str
    ramase: int | None = None
    total: int | None = None
    procent_folosit: float | None = None
    resetare_la: dt.datetime | None = None

    @property
    def aproape_epuizate(self) -> bool:
        if self.procent_folosit is not None and self.procent_folosit >= 80.0:
            return True
        return self.ramase is not None and self.total is not None and self.ramase <= max(1, self.total // 10)
