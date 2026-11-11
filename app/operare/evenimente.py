"""Jurnalul de evenimente (22.1): tranzițiile de stare și faptele de domeniu. Doar adăugări."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.operare import jurnale
from app.operare.modele import JurnalEveniment


def emite(
    db: Session,
    tip: str,
    *,
    sursa: str,
    obiect_tip: str | None = None,
    obiect_id: object | None = None,
    utilizator_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | str | None = jurnale.DIN_CONTEXT,
    date: dict[str, Any] | None = None,
) -> uuid.UUID:
    """Scrie un eveniment în tranzacția `db` (aceeași cu acțiunea)."""
    return jurnale.scrie(
        db,
        JurnalEveniment,
        {
            "tip": tip,
            "sursa": sursa,
            "obiect_tip": obiect_tip,
            "obiect_id": None if obiect_id is None else str(obiect_id),
            "date": jurnale.curata_detalii(date),
        },
        utilizator_id=utilizator_id,
        tenant_id=tenant_id,
    )
