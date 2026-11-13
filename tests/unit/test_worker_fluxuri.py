"""Workerul importă fiecare modul care declară fluxuri durabile (`@motor.flux`). Un modul uitat înseamnă
joburi puse în coadă
pe care workerul real nu le poate rula (găsit în F5.7: `app.validare.fluxuri` lipsea din listă)."""

import re
from pathlib import Path

from app import worker

ROOT = Path(__file__).resolve().parents[2]
EXCEPTII = {"app.operare.motor"}  # definește decoratorul, nu fluxuri


def _modul(cale: Path) -> str:
    rel = cale.relative_to(ROOT).with_suffix("")
    parti = rel.parts[:-1] if rel.name == "__init__" else rel.parts
    return ".".join(parti)


def test_fiecare_modul_cu_fluxuri_este_importat_de_worker() -> None:
    declarate = {
        _modul(p)
        for p in (ROOT / "app").rglob("*.py")
        if re.search(r"^@motor\.flux\(", p.read_text(encoding="utf-8"), re.M)
    }
    acoperite = {m for m in declarate if any(m == x or m.startswith(x + ".") for x in worker.MODULE_FLUXURI)}
    # app.operare.efecte este pachet: executorul lui e importat de `app.operare.efecte`
    acoperite |= {m for m in declarate if m.startswith("app.operare.efecte.")}
    lipsa = declarate - acoperite - EXCEPTII
    assert not lipsa, f"module cu fluxuri pe care workerul nu le importă: {sorted(lipsa)}"
    assert {"app.validare.fluxuri", "app.validare.banc.fluxuri"} <= set(worker.MODULE_FLUXURI)
