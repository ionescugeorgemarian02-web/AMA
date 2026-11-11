"""Starea backup-ului, citită din fișierele JSON scrise de serviciul `backup` (contract: docs/specs/F1.9.md).

Nu rulează nimic și nu scrie nimic. Fișier lipsă = „nerulat”; fișier corupt sau cu altă schemă = „necitibil”
(fără excepții). NU face parte din `/readyz`: o stare proastă a backup-ului nu are voie să blocheze livrările.
"""

import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import get_settings
from app.operare.health import Indicator

SCHEMA = "ama.backup/1"
PRAG_BACKUP = timedelta(hours=26)
PRAG_RESTAURARE = timedelta(days=8)
FISIERE = {
    "backup": "ultimul-backup.json",
    "restaurare_test": "ultima-restaurare-test.json",
    "curatare": "ultima-curatare.json",
}
ISTORIC = "istoric.jsonl"
MAXIM_FISIER = 1_000_000  # octeți; fișierele reale au câțiva KB
MAXIM_ISTORIC = 2_000_000  # se citește doar sfârșitul


class Artefact(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nume: str
    octeti: int = 0
    sha256: str = ""


class Rezultat(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    schema_: Literal["ama.backup/1"] = Field(alias="schema")
    tip: Literal["backup", "restaurare_test", "curatare"]
    stare: Literal["reusit", "esuat"]
    inceput: datetime
    sfarsit: datetime | None = None
    versiune: str | None = None
    durata_s: float | None = None
    destinatie: str | None = None
    eroare: str | None = Field(default=None, max_length=1000)
    id: str | None = None
    artefacte: list[Artefact] = []
    omise: list[str] = []


class Eticheta(StrEnum):
    NERULAT = "nerulat"
    OK = "ok"
    INVECHIT = "invechit"
    ESUAT = "esuat"
    NECITIBIL = "necitibil"


class Evaluare(BaseModel):
    eticheta: Eticheta
    ultim: Rezultat | None = None  # ultimul rezultat, oricare ar fi el
    ultim_reusit: Rezultat | None = None
    detaliu: str = ""

    @property
    def bun(self) -> bool:
        return self.eticheta is Eticheta.OK


class StareBackup(BaseModel):
    configurat: bool
    backup: Evaluare
    restaurare_test: Evaluare

    @property
    def bun(self) -> bool:
        return self.backup.bun and self.restaurare_test.bun


def _acum() -> datetime:
    return datetime.now(UTC)


def _aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def _citeste_text(cale: Path, maxim: int) -> str | None:
    try:
        with cale.open("rb") as f:
            f.seek(0, 2)
            dim = f.tell()
            f.seek(max(0, dim - maxim))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return None


def _rezultat_din_fisier(cale: Path) -> tuple[Rezultat | None, str]:
    """(rezultat, eroare). Ambele None/gol dacă fișierul lipsește."""
    if not cale.exists():
        return None, ""
    text = _citeste_text(cale, MAXIM_FISIER)
    if text is None:
        return None, "fișier ilizibil"
    try:
        return Rezultat.model_validate(json.loads(text)), ""
    except (ValueError, ValidationError):
        return None, "fișier corupt sau cu altă schemă"


def _din_istoric(director: Path, tip: str) -> Rezultat | None:
    """Ultimul rezultat `reusit` de acest tip din istoric; liniile corupte se sar."""
    text = _citeste_text(director / ISTORIC, MAXIM_ISTORIC)
    if not text:
        return None
    for linie in reversed(text.splitlines()):
        try:
            r = Rezultat.model_validate(json.loads(linie))
        except (ValueError, ValidationError):
            continue
        if r.tip == tip and r.stare == "reusit":
            return r
    return None


def _evalueaza(director: Path, tip: str, prag: timedelta, acum: datetime) -> Evaluare:
    ultim, eroare = _rezultat_din_fisier(director / FISIERE[tip])
    if eroare:
        return Evaluare(eticheta=Eticheta.NECITIBIL, detaliu=eroare)
    if ultim is None:
        return Evaluare(eticheta=Eticheta.NERULAT, detaliu="încă nu a rulat")
    reusit = ultim if ultim.stare == "reusit" else _din_istoric(director, tip)
    if ultim.stare == "esuat":
        return Evaluare(
            eticheta=Eticheta.ESUAT, ultim=ultim, ultim_reusit=reusit, detaliu=ultim.eroare or "eșuat"
        )
    if acum - _aware(ultim.inceput) > prag:
        return Evaluare(eticheta=Eticheta.INVECHIT, ultim=ultim, ultim_reusit=reusit, detaliu="prea vechi")
    return Evaluare(eticheta=Eticheta.OK, ultim=ultim, ultim_reusit=reusit)


def citeste_stare(director: str | Path | None = None, *, acum: datetime | None = None) -> StareBackup:
    """Starea curentă. `director` implicit: `AMA_BACKUP_STATUS_DIR`; nesetat = `configurat=False`."""
    brut = str(director) if director is not None else get_settings().backup_status_dir
    moment = acum or _acum()
    if not brut:
        gol = Evaluare(eticheta=Eticheta.NERULAT, detaliu="directorul de stare nu este configurat")
        return StareBackup(configurat=False, backup=gol, restaurare_test=gol)
    d = Path(brut)
    return StareBackup(
        configurat=True,
        backup=_evalueaza(d, "backup", PRAG_BACKUP, moment),
        restaurare_test=_evalueaza(d, "restaurare_test", PRAG_RESTAURARE, moment),
    )


def rezumat(stare: StareBackup | None = None) -> str:
    """O linie, fără date sensibile (pentru Telegram și Acasă)."""
    s = stare or citeste_stare()
    return f"backup {s.backup.eticheta.value}, test de restaurare {s.restaurare_test.eticheta.value}"


def indicator() -> Indicator:
    """Indicatorul de sănătate (în afara `/readyz`): „bun” doar dacă backup-ul și testul sunt în regulă."""
    s = citeste_stare()
    return Indicator(bun=s.configurat and s.bun, detaliu=rezumat(s))
