"""Înscrierea (F7.6, pâlnia din docs/04: audit → plată → onboarding): firma alege planul, se creează clientul
și abonamentul; plata se face pe pagina procesatorului. Din raportul de audit, lead-ul trece în `client`."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import finante
from app.conturi import Actor, DateInvalide, creeaza_client
from app.site import audit as audit_site
from app.site.modele import Lead


def inscrie(
    db: Session, *, firma: str, email: str, plan: str, lead_id: uuid.UUID | None = None
) -> tuple[uuid.UUID, str]:
    """Creează clientul și abonamentul. Întoarce (abonament, jetonul paginii de plată)."""
    email = email.strip().lower()
    if not audit_site.EMAIL.match(email):
        raise DateInvalide("Adresa de email nu este validă.")
    client = creeaza_client(db, firma, actor=Actor(None, None, "sistem"))
    if lead_id is not None:
        lead = db.execute(select(Lead).where(Lead.id == lead_id).with_for_update()).scalar_one_or_none()
        if lead is not None and lead.tenant_id is None:
            lead.stare, lead.tenant_id = "client", client.id
    try:
        a, jeton = finante.abonamente.incepe(db, client.id, plan, email=email)
    except ValueError as exc:
        raise DateInvalide(str(exc)) from exc
    return a.id, jeton
