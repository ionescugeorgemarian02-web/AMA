"""Accesul la rândurile cererilor de aprobare, fără logica de decizie (o folosesc `tranzitii` și `aprobari`).

Separat de `aprobari` ca să nu existe import circular: `tranzitii.muta` verifică temeiul unei mutări citind
cererea, iar `aprobari` mută livrabilul prin `tranzitii.muta`.
"""

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ids import new_id
from app.productie.modele import Aprobare, Livrabil
from app.productie.reguli_aprobare import Decident, StareAprobare


def gaseste(db: Session, aprobare_id: uuid.UUID, *, blocheaza: bool = False) -> Aprobare | None:
    q = select(Aprobare).where(Aprobare.id == aprobare_id).execution_options(populate_existing=True)
    if blocheaza:
        q = q.with_for_update()
    return db.execute(q).scalar_one_or_none()


def in_asteptare(db: Session, livrabil_id: uuid.UUID) -> Aprobare | None:
    return db.execute(
        select(Aprobare).where(
            Aprobare.livrabil_id == livrabil_id, Aprobare.stare == StareAprobare.IN_ASTEPTARE.value
        )
    ).scalar_one_or_none()


def deschide(
    db: Session,
    livrabil: Livrabil,
    decident: Decident,
    *,
    termen_la: dt.datetime,
    reamintire_la: dt.datetime,
    creat_de: uuid.UUID | None,
) -> Aprobare:
    """O cerere nouă pentru versiunea CURENTĂ a livrabilului (indicele unic refuză o a doua în așteptare)."""
    ap = Aprobare(
        id=new_id(),
        tenant_id=livrabil.tenant_id,
        livrabil_id=livrabil.id,
        versiune=livrabil.versiune,
        clasa_actiune=livrabil.clasa_actiune,
        decident=decident.value,
        stare=StareAprobare.IN_ASTEPTARE.value,
        termen_la=termen_la,
        reamintire_la=reamintire_la,
        creat_de=creat_de,
    )
    db.add(ap)
    db.flush()
    return ap


def anuleaza_in_asteptare(db: Session, livrabil_id: uuid.UUID) -> Aprobare | None:
    """Anulează cererea în așteptare a livrabilului (de exemplu pentru că s-a născut o versiune nouă)."""
    ap = db.execute(
        select(Aprobare)
        .where(Aprobare.livrabil_id == livrabil_id, Aprobare.stare == StareAprobare.IN_ASTEPTARE.value)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if ap is not None:
        ap.stare = StareAprobare.ANULAT.value
        ap.decis_la = func.now()
        db.flush()
    return ap
