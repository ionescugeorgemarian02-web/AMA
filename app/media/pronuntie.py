"""Dicționarul de pronunție pe client (F8.2) și normalizarea textului pentru vocea lui."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.media import normalizare
from app.media.modele import Pronuntie


def adauga(
    db: Session, tenant_id: uuid.UUID, termen: str, pronuntie: str, *, utilizator_id: uuid.UUID | None = None
) -> Pronuntie:
    """Adaugă sau înlocuiește pronunția unui termen (fără cifre: se citește exact cum e scrisă)."""
    t, p = termen.strip(), normalizare.normalizeaza(pronuntie.strip())
    existent = db.execute(
        select(Pronuntie).where(Pronuntie.tenant_id == tenant_id, func.lower(Pronuntie.termen) == t.lower())
    ).scalar_one_or_none()
    if existent is not None:
        existent.pronuntie = p
        db.flush()
        return existent
    r = Pronuntie(tenant_id=tenant_id, termen=t, pronuntie=p, creat_de=utilizator_id)
    db.add(r)
    db.flush()
    return r


def dictionar(db: Session, tenant_id: uuid.UUID) -> dict[str, str]:
    rows = db.execute(select(Pronuntie).where(Pronuntie.tenant_id == tenant_id)).scalars()
    return {r.termen: r.pronuntie for r in rows}


def pentru_voce(db: Session, tenant_id: uuid.UUID, text: str) -> str:
    """Textul normalizat cu dicționarul clientului: ce primește motorul de voce."""
    return normalizare.normalizeaza(text, dictionar(db, tenant_id))
