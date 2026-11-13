"""Rulările bancului salvate (tabelul `banc_rulari`, nivel de agenție)."""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ids import new_id
from app.validare.modele import BancRulare


def porneste(db: Session, *, utilizator_id: uuid.UUID | None, cheie: str | None = None) -> BancRulare:
    """O rulare nouă `în curs`. Aceeași cheie de două ori întoarce rularea existentă (idempotent)."""
    if cheie is not None:
        existenta = db.execute(select(BancRulare).where(BancRulare.cheie == cheie)).scalar_one_or_none()
        if existenta is not None:
            return existenta
    r = BancRulare(id=new_id(), cheie=cheie, pornit_de=utilizator_id, stare="in_curs")
    db.add(r)
    db.flush()
    return r


def termina(db: Session, rulare_id: uuid.UUID, scoruri: dict[str, Any]) -> BancRulare:
    r = db.get(BancRulare, rulare_id)
    if r is None:
        raise LookupError(str(rulare_id))
    r.stare, r.scoruri, r.exemple = "terminat", scoruri, int(scoruri.get("exemple", 0))
    r.amprenta_seturi = str(scoruri.get("amprenta_seturi", ""))[:64]
    r.terminat_la = func.now()
    db.flush()
    return r


def esueaza(db: Session, rulare_id: uuid.UUID, eroare: str) -> None:
    r = db.get(BancRulare, rulare_id)
    if r is not None:
        r.stare, r.eroare, r.terminat_la = "esuat", eroare[:500], func.now()
        db.flush()


def citeste(db: Session, rulare_id: uuid.UUID) -> BancRulare | None:
    return db.get(BancRulare, rulare_id)


def recente(db: Session, limita: int = 10) -> list[BancRulare]:
    return list(
        db.execute(
            select(BancRulare).order_by(BancRulare.pornit_la.desc(), BancRulare.id.desc()).limit(limita)
        )
        .scalars()
        .all()
    )


def ultima_terminata(db: Session) -> BancRulare | None:
    return db.execute(
        select(BancRulare)
        .where(BancRulare.stare == "terminat")
        .order_by(BancRulare.pornit_la.desc(), BancRulare.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def in_curs(db: Session, *, de_la: dt.datetime | None = None) -> BancRulare | None:
    q = select(BancRulare).where(BancRulare.stare == "in_curs")
    if de_la is not None:
        q = q.where(BancRulare.pornit_la >= de_la)
    return db.execute(q.order_by(BancRulare.pornit_la.desc()).limit(1)).scalar_one_or_none()
