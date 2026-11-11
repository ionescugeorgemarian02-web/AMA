"""Verificarea de sănătate. Verificările suplimentare (bază, cozi) se înregistrează pe măsură ce apar."""

from collections.abc import Callable

from fastapi import APIRouter, Response

from app import __version__
from app.config import get_settings

router = APIRouter(tags=["operare"])

# nume -> funcție care aruncă excepție dacă dependența nu răspunde
_checks: dict[str, Callable[[], None]] = {}


def register_check(name: str, check: Callable[[], None]) -> None:
    _checks[name] = check


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Procesul este pornit. Nu atinge dependențe."""
    settings = get_settings()
    return {"status": "ok", "version": settings.version, "app": __version__, "env": settings.env}


@router.get("/readyz")
def readyz(response: Response) -> dict[str, object]:
    """Dependențele răspund. Folosit de livrare înainte de mutarea traficului."""
    results: dict[str, str] = {}
    for name, check in _checks.items():
        try:
            check()
            results[name] = "ok"
        except Exception as exc:
            results[name] = f"eroare: {type(exc).__name__}"
    ok = all(v == "ok" for v in results.values())
    if not ok:
        response.status_code = 503
    return {"status": "ok" if ok else "degradat", "checks": results}
