"""Întrebările către client (docs/09 §9.3): „dacă lipsește un fapt necesar, livrabilul se oprește cu o
întrebare către client,
nu cu o presupunere”. O întrebare este o înregistrare vizibilă (ecranul Producție, lista de întrebări
deschise), legată de
livrabil și de versiunea lui. Răspunsul NU devine fapt: faptul îl propune și îl aprobă un om în Creier; apoi
un om reia
livrabilul (`productie.reia_de_om`), care revine în validare și găsește faptul.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ids import new_id
from app.operare import audit
from app.validare.modele import Intrebare


class IntrebareInchisa(ValueError):
    pass


def deschide(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    livrabil_id: uuid.UUID,
    versiune: int,
    validator: str,
    intrebare: str,
    tip_fapt: str | None = None,
    subiect: str | None = None,
) -> Intrebare:
    """Deschide întrebarea; aceeași întrebare pentru aceeași versiune nu se dublează."""
    existenta = db.execute(
        select(Intrebare).where(
            Intrebare.livrabil_id == livrabil_id,
            Intrebare.versiune == versiune,
            Intrebare.intrebare == intrebare,
        )
    ).scalar_one_or_none()
    if existenta is not None:
        return existenta
    r = Intrebare(
        id=new_id(), tenant_id=tenant_id, livrabil_id=livrabil_id, versiune=versiune, validator=validator,
        intrebare=intrebare, tip_fapt=tip_fapt, subiect=subiect,
    )  # fmt: skip
    db.add(r)
    db.flush()
    audit.record(
        db,
        "validare.intrebare_deschisa",
        obiect_tip="livrabil",
        obiect_id=livrabil_id,
        tenant_id=tenant_id,
        actor_tip="sistem",
        detalii={"validator": validator, "versiune": versiune, "tip_fapt": tip_fapt or ""},
    )
    return r


def ale_livrabilului(db: Session, livrabil_id: uuid.UUID) -> list[Intrebare]:
    return list(
        db.execute(
            select(Intrebare)
            .where(Intrebare.livrabil_id == livrabil_id)
            .order_by(Intrebare.creat_la, Intrebare.id)
        ).scalars()
    )


def deschise(db: Session, *, limita: int = 100) -> list[Intrebare]:
    """Întrebările fără răspuns, cele mai vechi întâi (pentru biroul de aprobări, F5.9)."""
    return list(
        db.execute(
            select(Intrebare)
            .where(Intrebare.stare == "deschisa")
            .order_by(Intrebare.creat_la, Intrebare.id)
            .limit(limita)
        ).scalars()
    )


def raspunde(db: Session, intrebare_id: uuid.UUID, raspuns: str, *, utilizator_id: uuid.UUID) -> Intrebare:
    """Notează răspunsul clientului. Nu creează niciun fapt; vezi docstring-ul modulului."""
    r = db.get(Intrebare, intrebare_id)
    if r is None:
        raise LookupError(str(intrebare_id))
    if r.stare != "deschisa":
        raise IntrebareInchisa(f"întrebarea e „{r.stare}”")
    raspuns = raspuns.strip()
    if len(raspuns) < 2:
        raise ValueError("răspunsul nu poate fi gol")
    r.stare, r.raspuns, r.raspuns_de, r.raspuns_la = (
        "raspunsa",
        raspuns,
        utilizator_id,
        dt.datetime.now(dt.UTC),
    )
    db.flush()
    audit.record(
        db,
        "validare.intrebare_raspunsa",
        obiect_tip="livrabil",
        obiect_id=r.livrabil_id,
        utilizator_id=utilizator_id,
        tenant_id=r.tenant_id,
        detalii={"validator": r.validator, "versiune": r.versiune},
    )
    return r


def inchide(db: Session, intrebare_id: uuid.UUID, *, utilizator_id: uuid.UUID, motiv: str) -> Intrebare:
    """Întrebarea nu mai e necesară (livrabilul s-a schimbat sau a fost anulat)."""
    r = db.get(Intrebare, intrebare_id)
    if r is None:
        raise LookupError(str(intrebare_id))
    if r.stare != "deschisa":
        raise IntrebareInchisa(f"întrebarea e „{r.stare}”")
    r.stare, r.raspuns, r.raspuns_de, r.raspuns_la = (
        "inchisa",
        motiv.strip()[:4000],
        utilizator_id,
        dt.datetime.now(dt.UTC),
    )
    db.flush()
    return r


def pentru_ecran(db: Session, livrabil_id: uuid.UUID) -> list[dict[str, Any]]:
    return [{"i": i} for i in ale_livrabilului(db, livrabil_id)]
