"""Fluxul durabil al colectorului (F4.2): `cercetare.colecteaza_site(tenant_id, colectare_id)` pe coada `io`.

Primește doar identificatori. Fiecare pas citește frontiera din bază și scrie rezultatul în bază; rezultatele
pașilor sunt cuvinte scurte. Un pas întrerupt se reia (cel puțin o dată): citirea unei pagini este idempotentă
(un document pe (sursă, adresă); o pagină deja înregistrată nu se mai înregistrează).
"""

import uuid

from app.cercetare import colectare
from app.operare import motor
from app.operare.motor import Coada, Prioritate

NUME_FLUX = "cercetare.colecteaza_site"
LOTURI_MAXIME = 400  # plasă de siguranță: limita de pagini oprește colectarea mult înainte


@motor.pas(nume="cercetare.initializeaza", reincercari=2)
def _initializeaza(tenant_id: str, colectare_id: str) -> str:
    return colectare.initializeaza(uuid.UUID(tenant_id), uuid.UUID(colectare_id))


@motor.pas(nume="cercetare.lot", reincercari=1)
def _lot(tenant_id: str, colectare_id: str) -> str:
    return colectare.proceseaza_lot(uuid.UUID(tenant_id), uuid.UUID(colectare_id))


@motor.pas(nume="cercetare.incheie", reincercari=2)
def _incheie(tenant_id: str, colectare_id: str) -> str:
    return colectare.incheie(uuid.UUID(tenant_id), uuid.UUID(colectare_id))


@motor.flux(NUME_FLUX, timp_maxim_sec=900)
def colecteaza_site(tenant_id: str, colectare_id: str) -> str:
    _initializeaza(tenant_id, colectare_id)
    for _ in range(LOTURI_MAXIME):
        if _lot(tenant_id, colectare_id) == "gata":
            break
    return _incheie(tenant_id, colectare_id)


def trimite(tenant_id: uuid.UUID, colectare_id: uuid.UUID) -> str:
    """Pune colectarea în coadă (idempotent pe `colectare_id`). Întoarce identificatorul jobului."""
    return motor.trimite(
        colecteaza_site, str(tenant_id), str(colectare_id), coada=Coada.IO, prioritate=Prioritate.P2,
        cheie=f"colectare:{colectare_id}",
    )  # fmt: skip
