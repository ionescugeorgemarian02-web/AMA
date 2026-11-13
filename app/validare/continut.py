"""Conținutul livrabilului (ACOPERIRE PROVIZORIE până la F6, vezi docs/specs/F5.1.md).

O versiune de conținut = text + câmpuri pe canal + active declarate, legată de `livrabile.versiune`. Se
scrie doar
adăugând: o versiune are un singur conținut. Dacă versiunea curentă are deja conținut, `scrie` ridică
versiunea cu
`productie.versiune_noua` (ceea ce anulează și orice aprobare legată de versiunea veche).
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import productie
from app.ids import new_id
from app.validare.intrare import Continut, amprenta_text
from app.validare.modele import ContinutLivrabil


class FaraContinut(LookupError):
    """Livrabilul nu are conținut pentru versiunea cerută."""


def _din_rand(r: ContinutLivrabil) -> Continut:
    return Continut(
        versiune=r.versiune,
        text=r.text,
        campuri=dict(r.campuri),
        active=tuple(r.active),
        autor=r.autor,
        model_autor=r.model_autor,
    )


def rand(db: Session, livrabil_id: uuid.UUID, versiune: int) -> ContinutLivrabil | None:
    return db.execute(
        select(ContinutLivrabil).where(
            ContinutLivrabil.livrabil_id == livrabil_id, ContinutLivrabil.versiune == versiune
        )
    ).scalar_one_or_none()


def citeste(db: Session, livrabil_id: uuid.UUID, versiune: int | None = None) -> Continut:
    """Conținutul versiunii cerute (implicit cea curentă a livrabilului)."""
    if versiune is None:
        livrabil = productie.citeste(db, livrabil_id)
        if livrabil is None:
            raise productie.LivrabilInexistent(str(livrabil_id))
        versiune = livrabil.versiune
    r = rand(db, livrabil_id, versiune)
    if r is None:
        raise FaraContinut(f"livrabilul {livrabil_id} nu are conținut pentru versiunea {versiune}")
    return _din_rand(r)


def versiuni(db: Session, livrabil_id: uuid.UUID) -> list[ContinutLivrabil]:
    return list(
        db.execute(
            select(ContinutLivrabil)
            .where(ContinutLivrabil.livrabil_id == livrabil_id)
            .order_by(ContinutLivrabil.versiune)
        ).scalars()
    )


def scrie(
    db: Session,
    livrabil_id: uuid.UUID,
    *,
    text: str,
    campuri: dict[str, Any] | None = None,
    active: list[dict[str, Any]] | None = None,
    autor: str,
    model_autor: str | None = None,
    utilizator_id: uuid.UUID | None = None,
) -> ContinutLivrabil:
    """Conținutul versiunii curente; dacă ea are deja conținut, ridică versiunea și scrie în cea nouă."""
    livrabil = productie.blocheaza(db, livrabil_id)
    if rand(db, livrabil.id, livrabil.versiune) is not None:
        productie.versiune_noua(
            db, livrabil.id, componenta=autor, motiv="conținut nou", utilizator_id=utilizator_id
        )
        db.refresh(livrabil)
    campuri = dict(campuri or {})
    r = ContinutLivrabil(
        id=new_id(),
        tenant_id=livrabil.tenant_id,
        livrabil_id=livrabil.id,
        versiune=livrabil.versiune,
        text=text,
        campuri=campuri,
        active=list(active or []),
        autor=autor[:60],
        model_autor=model_autor,
        amprenta=amprenta_text(text, campuri),
        creat_de=utilizator_id,
    )
    db.add(r)
    db.flush()
    return r
