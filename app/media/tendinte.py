"""Inboxul de tendințe (F7.5, docs/19 §19.2): clientul lipește linkuri și idei; cercetarea le folosește
(F10)."""

import uuid
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.media.modele import Tendinta
from app.operare import audit


class TendintaInvalida(ValueError):
    pass


def adauga(db: Session, tenant_id: uuid.UUID, text: str, *, utilizator_id: uuid.UUID | None) -> Tendinta:
    """Un link (primul cuvânt, dacă e o adresă http/https) cu o notă, sau doar o idee."""
    text = text.strip()
    if not 3 <= len(text) <= 2000:
        raise TendintaInvalida("scrie între 3 și 2000 de caractere")
    primul = text.split()[0]
    url = None
    if primul.lower().startswith(("http://", "https://")):
        p = urlsplit(primul)
        if not p.hostname or "." not in p.hostname or len(primul) > 500:
            raise TendintaInvalida("linkul nu este valid")
        url = primul
    t = Tendinta(tenant_id=tenant_id, text=text, url=url, creat_de=utilizator_id)
    db.add(t)
    db.flush()
    audit.record(
        db,
        "tendinta.adaugata",
        obiect_tip="tendinta",
        obiect_id=t.id,
        tenant_id=tenant_id,
        utilizator_id=utilizator_id,
        detalii={"cu_link": url is not None},
    )
    return t


def ale_clientului(db: Session, tenant_id: uuid.UUID, *, limita: int = 50) -> list[Tendinta]:
    return list(
        db.execute(
            select(Tendinta)
            .where(Tendinta.tenant_id == tenant_id)
            .order_by(Tendinta.creat_la.desc())
            .limit(limita)
        ).scalars()
    )
