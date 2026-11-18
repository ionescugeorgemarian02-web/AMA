"""Presiunea pe resurse (docs/25 §25.3, F15.1): discul la 85% și memoria aproape de limită.

- Discul la `PRAG_DISC`: se curăță fișierele parțiale rămase (randări întrerupte, scrieri temporare),
  randările noi nu mai pornesc (se amână singure) și pleacă o alertă critică, o dată pe trecerea peste prag.
- Memoria la `PRAG_MEMORIE`: joburile grele (randări) se amână; serviciile permanente (web, worker, cozile
  `urgent` / `io`) nu sunt atinse: nimic nu se oprește, doar culoarele grele nu mai pornesc munca nouă.

Măsurarea citește discul directorului media și memoria din cgroup v2 (containerul), altfel din
`/proc/meminfo`.
În teste, măsurarea se înlocuiește cu `seteaza_masurare` (simularea unui disc plin sau a memoriei la limită).
"""

import datetime as dt
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.logging import get_logger

log = get_logger(__name__)

PRAG_DISC = 85.0  # [I] docs/25 §25.3
PRAG_MEMORIE = 90.0  # [I] „se apropie de limită”
AMANARE_GREU = dt.timedelta(minutes=10)  # [I] după cât reîncearcă un job greu amânat
VARSTA_PARTIALE = dt.timedelta(hours=1)  # [I] un fișier parțial mai vechi de atât nu mai e în lucru
DIR_LUCRU = ".lucru"  # sub directorul media: directoarele de lucru ale randărilor


@dataclass(frozen=True)
class Masurare:
    disc_pct: float
    memorie_pct: float

    @property
    def disc_plin(self) -> bool:
        return self.disc_pct >= PRAG_DISC

    @property
    def memorie_la_limita(self) -> bool:
        return self.memorie_pct >= PRAG_MEMORIE


_masurare: Callable[[], Masurare] | None = None
_ultima_stare: dict[str, bool] = {"disc": False, "memorie": False}


def seteaza_masurare(f: Callable[[], Masurare] | None) -> None:
    """# SIMULAT în teste: înlocuiește măsurarea reală (None = înapoi la cea reală)."""
    global _masurare
    _masurare = f
    _ultima_stare.update(disc=False, memorie=False)


def _memorie_pct() -> float:
    cg = Path("/sys/fs/cgroup")
    try:
        maxim = (cg / "memory.max").read_text().strip()
        if maxim != "max":
            return 100.0 * int((cg / "memory.current").read_text()) / int(maxim)
    except (OSError, ValueError):
        pass
    try:
        info = {
            r.split(":")[0]: int(r.split()[1])
            for r in Path("/proc/meminfo").read_text().splitlines()
            if ":" in r
        }
        return 100.0 * (1 - info["MemAvailable"] / info["MemTotal"])
    except (OSError, KeyError, ValueError, ZeroDivisionError):
        return 0.0


def masoara() -> Masurare:
    if _masurare is not None:
        return _masurare()
    cale = Path(get_settings().media_dir)
    while not cale.exists() and cale != cale.parent:
        cale = cale.parent
    total, folosit, _ = shutil.disk_usage(cale)
    return Masurare(disc_pct=100.0 * folosit / total if total else 0.0, memorie_pct=_memorie_pct())


def permite_greu(m: Masurare | None = None) -> tuple[bool, str]:
    """Poate porni acum un job greu nou? Întoarce (da/nu, motivul: `disc` / `memorie` / '')."""
    m = m or masoara()
    if m.disc_plin:
        return False, "disc"
    if m.memorie_la_limita:
        return False, "memorie"
    return True, ""


def director_lucru(nume: str) -> Path:
    """Directorul de lucru al unei randări; ce a rămas de la o rulare întreruptă se șterge la pornire."""
    d = Path(get_settings().media_dir) / DIR_LUCRU / nume
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    return d


def curata_partiale(*, varsta: dt.timedelta = VARSTA_PARTIALE) -> int:
    """Șterge fișierele parțiale vechi: directoarele de lucru și scrierile temporare (`.*.tmp`)."""
    baza = Path(get_settings().media_dir)
    prag = time.time() - varsta.total_seconds()
    sterse = 0
    lucru = baza / DIR_LUCRU
    if lucru.is_dir():
        for d in lucru.iterdir():
            if d.stat().st_mtime < prag:
                shutil.rmtree(d, ignore_errors=True) if d.is_dir() else d.unlink(missing_ok=True)
                sterse += 1
    if baza.is_dir():
        for f in baza.glob("*/active/.*.tmp"):
            if f.stat().st_mtime < prag:
                f.unlink(missing_ok=True)
                sterse += 1
    return sterse


def verifica() -> dict[str, object]:
    """Ticul de resurse: măsoară, curăță la disc plin și alertează o dată pe trecerea peste prag."""
    from app.operare import alerte

    m = masoara()
    sterse = curata_partiale() if m.disc_plin else 0
    if m.disc_plin and not _ultima_stare["disc"]:
        alerte.trimite(
            "critic",
            "Discul a ajuns la " + f"{m.disc_pct:.0f}%",
            f"Am șters {sterse} fișiere parțiale; randările noi se amână până scade sub {PRAG_DISC:.0f}%.",
        )
    if m.memorie_la_limita and not _ultima_stare["memorie"]:
        alerte.trimite(
            "important",
            "Memoria aproape de limită",
            f"Memoria e la {m.memorie_pct:.0f}%; joburile grele se amână, serviciile permanente merg.",
        )
    _ultima_stare.update(disc=m.disc_plin, memorie=m.memorie_la_limita)
    log.info("resurse", extra={"disc_pct": round(m.disc_pct, 1), "memorie_pct": round(m.memorie_pct, 1)})
    return {"disc_pct": m.disc_pct, "memorie_pct": m.memorie_pct, "sterse": sterse}
