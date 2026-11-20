"""Cererile de material lipsă (F-editorial, decizia 3): o prezentare a afacerii reale fără fotografia
potrivită blochează livrabilul cu o cerere precisă, vizibilă în panou; după încărcare, livrabilul se reia."""

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ids import new_id
from app.media.modele import CerereMaterial
from app.media.regizor import Storyboard
from app.operare import audit


def deschide(db: Session, tenant_id: uuid.UUID, livrabil_id: uuid.UUID, versiune: int, sb: Storyboard) -> int:
    """Înregistrează (sau redeschide) câte o cerere pe scena lipsă; idempotent pe (livrabil, versiune,
    scenă)."""
    cereri = sb.cereri()
    for scena, subiect, text in cereri:
        db.execute(
            insert(CerereMaterial)
            .values(id=new_id(), tenant_id=tenant_id, livrabil_id=livrabil_id, versiune=versiune, scena=scena,
                    subiect=subiect, cerere=text, stare="deschisa")
            .on_conflict_do_update(
                index_elements=["tenant_id", "livrabil_id", "versiune", "scena"],
                set_={"subiect": subiect, "cerere": text, "stare": "deschisa", "rezolvat_la": None},
            )
        )  # fmt: skip
    audit.record(
        db,
        "livrabil.material_lipsa",
        obiect_tip="livrabil",
        obiect_id=livrabil_id,
        tenant_id=tenant_id,
        detalii={"versiune": versiune, "scene": [c[0] for c in cereri]},
    )
    return len(cereri)


VERSIUNE_IDEE = 0  # cererile etapei de idee vin înaintea oricărei versiuni de conținut


def cere_filmare(
    db: Session, tenant_id: uuid.UUID, livrabil_id: uuid.UUID, cadre: list[tuple[int, str, str]]
) -> int:
    """Cererile de filmare ale conceptului ales (F-idee): un cadru de material propriu pe care clientul nu îl
    are încă. `cadre`: (numărul cadrului, subiectul, cererea); versiunea 0, scena = numărul cadrului."""
    for scena, subiect, text in cadre:
        db.execute(
            insert(CerereMaterial)
            .values(id=new_id(), tenant_id=tenant_id, livrabil_id=livrabil_id, versiune=VERSIUNE_IDEE,
                    scena=scena, subiect=subiect, cerere=text, stare="deschisa")
            .on_conflict_do_update(
                index_elements=["tenant_id", "livrabil_id", "versiune", "scena"],
                set_={"subiect": subiect, "cerere": text, "stare": "deschisa", "rezolvat_la": None},
            )
        )  # fmt: skip
    audit.record(
        db,
        "livrabil.filmare_ceruta",
        obiect_tip="livrabil",
        obiect_id=livrabil_id,
        tenant_id=tenant_id,
        detalii={"cadre": [c[0] for c in cadre]},
    )
    return len(cadre)


def deschise(db: Session, tenant_id: uuid.UUID, livrabil_id: uuid.UUID | None = None) -> list[CerereMaterial]:
    q = select(CerereMaterial).where(
        CerereMaterial.tenant_id == tenant_id, CerereMaterial.stare == "deschisa"
    )
    if livrabil_id is not None:
        q = q.where(CerereMaterial.livrabil_id == livrabil_id)
    return list(db.scalars(q.order_by(CerereMaterial.creat_la, CerereMaterial.scena)))


def rezolva(db: Session, tenant_id: uuid.UUID, livrabil_id: uuid.UUID) -> int:
    """Închide cererile deschise ale livrabilului (la reluare sau când storyboardul are tot materialul)."""
    c = deschise(db, tenant_id, livrabil_id)
    acum = dt.datetime.now(dt.UTC)
    for x in c:
        x.stare, x.rezolvat_la = "rezolvata", acum
    db.flush()
    return len(c)
