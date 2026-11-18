"""Sănătatea pe MODEL (G-pool, portată din `model_health` al fabricii), peste întrerupătorul pe furnizor
(F3.4).

Un furnizor sănătos poate avea un model care nu mai există (404 / `not_found`, identificatorii se schimbă des)
sau care cade în buclă. Regulile, ca date:
- 404 → modelul e scos din rutare `PAUZA_INEXISTENT` (o zi): nu-l mai încercăm la fiecare apel;
- `PRAG_ERORI` erori de server / rețea consecutive → pauză `PAUZA_ERORI`;
- un succes șterge istoricul modelului.
Starea e în memoria procesului (fiecare proces își învață singur modelele bolnave; întrerupătorul din bază
rămâne sursa comună pentru furnizori). Fiecare pauză lasă o urmă (`gateway` / `model_indisponibil`).
"""

import datetime as dt
import threading
from dataclasses import dataclass

from app.gateway import ceas
from app.gateway.erori import EroareFurnizor
from app.operare import urme

PRAG_ERORI = 3
PAUZA_ERORI = dt.timedelta(minutes=5)
PAUZA_INEXISTENT = dt.timedelta(hours=24)


@dataclass
class _Stare:
    erori: int = 0
    pana_la: dt.datetime | None = None
    motiv: str = ""


_stari: dict[str, _Stare] = {}
_lacat = threading.Lock()


def esec(cod_model: str, exc: EroareFurnizor, *, acum: dt.datetime | None = None) -> dt.datetime | None:
    """Înregistrează o eroare; întoarce sfârșitul pauzei dacă modelul tocmai a fost pus pe pauză."""
    acum = acum or ceas.acum()
    with _lacat:
        s = _stari.setdefault(cod_model, _Stare())
        if exc.fel == "cerere" and exc.status == 404:
            s.pana_la, s.motiv = acum + PAUZA_INEXISTENT, "model inexistent la furnizor (404)"
        elif exc.fel in ("server", "retea"):
            s.erori += 1
            if s.erori < PRAG_ERORI:
                return None
            s.pana_la, s.motiv, s.erori = acum + PAUZA_ERORI, f"{PRAG_ERORI} erori consecutive", 0
        else:
            return None
        pana_la, motiv = s.pana_la, s.motiv
    urme.emite(
        "gateway", "model_indisponibil", rezultat="blocat", motiv=motiv, obiect_tip="model_llm",
        obiect_id=cod_model, iesiri={"pana_la": pana_la.isoformat()},
    )  # fmt: skip
    return pana_la


def succes(cod_model: str) -> None:
    with _lacat:
        _stari.pop(cod_model, None)


def indisponibile(acum: dt.datetime | None = None) -> frozenset[str]:
    acum = acum or ceas.acum()
    with _lacat:
        return frozenset(k for k, s in _stari.items() if s.pana_la is not None and s.pana_la > acum)


def stare(cod_model: str) -> tuple[int, dt.datetime | None, str]:
    with _lacat:
        s = _stari.get(cod_model, _Stare())
        return s.erori, s.pana_la, s.motiv


def reseteaza() -> None:
    """Pentru teste și pentru repornirea manuală a unui model."""
    with _lacat:
        _stari.clear()
