"""Jurnalul de audit (21.3): cine a făcut ce, când, pe ce obiect. Doar adăugări, impus în bază."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.operare import jurnale
from app.operare.jurnale import ip_cerere
from app.operare.modele import JurnalAudit

__all__ = ["ip_cerere", "record"]


def record(
    db: Session,
    actiune: str,
    *,
    obiect_tip: str | None = None,
    obiect_id: object | None = None,
    rezultat: str = "ok",
    utilizator_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | str | None = jurnale.DIN_CONTEXT,
    actor_tip: str | None = None,
    detalii: dict[str, Any] | None = None,
    ip: str | None = None,
) -> uuid.UUID:
    """Scrie o intrare de audit în tranzacția `db`, deci în același commit/rollback cu acțiunea.

    Utilizatorul și clientul se iau din contextul sesiunii dacă nu sunt date. IP-ul și identificatorul de
    corelare vin din cererea curentă. `detalii` nu are voie să conțină secrete (chei ca parola, token, cod…).
    """
    ctx_user = db.info.get("ama_ctx")
    if actor_tip is None:
        actor_tip = "utilizator" if (utilizator_id or (ctx_user and ctx_user.user_id)) else "anonim"
    return jurnale.scrie(
        db,
        JurnalAudit,
        {
            "actor_tip": actor_tip,
            "actiune": actiune,
            "obiect_tip": obiect_tip,
            "obiect_id": None if obiect_id is None else str(obiect_id),
            "rezultat": rezultat,
            "ip": ip or ip_cerere.get(),
            "detalii": jurnale.curata_detalii(detalii),
        },
        utilizator_id=utilizator_id,
        tenant_id=tenant_id,
    )
