"""Rulările și verdictele salvate (doar adăugare). Citirea pentru ecran și pentru F5.7 / F5.8."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ids import new_id
from app.validare.agregare import Agregat, Decizie
from app.validare.intrare import Continut
from app.validare.modele import Rulare, VerdictSalvat
from app.validare.verdict import Treapta, Verdict


def salveaza(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    livrabil_id: uuid.UUID,
    versiune: int,
    runda: int,
    continut: Continut,
    verdicte: list[Verdict],
    agregat: Agregat,
    oprit_la: Treapta | None,
) -> Rulare:
    r = Rulare(
        id=new_id(),
        tenant_id=tenant_id,
        livrabil_id=livrabil_id,
        versiune=versiune,
        runda=runda,
        decizie=agregat.decizie.value,
        cere_om=agregat.cere_om,
        puncte=agregat.puncte,
        prag=agregat.prag,
        oprit_la_treapta=oprit_la.value if oprit_la else None,
        instructiune=agregat.instructiune,
        amprenta=continut.amprenta,
        cost=agregat.cost.json(),
    )
    db.add(r)
    db.flush()
    for v in verdicte:
        db.add(
            VerdictSalvat(
                id=new_id(),
                tenant_id=tenant_id,
                rulare_id=r.id,
                livrabil_id=livrabil_id,
                versiune=versiune,
                runda=runda,
                validator=v.validator,
                validator_versiune=v.versiune,
                treapta=v.treapta.value,
                rezultat=v.rezultat.value,
                severitate=v.severitate.value if v.severitate else None,
                scor=v.scor,
                dovezi=[d.json() for d in v.dovezi],
                instructiune=v.instructiune,
                cost=v.cost.json(),
                detalii=v.detalii,
                amprenta=continut.amprenta,
            )
        )
    db.flush()
    return r


def rulari(db: Session, livrabil_id: uuid.UUID) -> list[Rulare]:
    return list(
        db.execute(
            select(Rulare).where(Rulare.livrabil_id == livrabil_id).order_by(Rulare.creat_la, Rulare.id)
        ).scalars()
    )


def verdicte(
    db: Session, livrabil_id: uuid.UUID, *, versiune: int | None = None, validator: str | None = None
) -> list[VerdictSalvat]:
    q = select(VerdictSalvat).where(VerdictSalvat.livrabil_id == livrabil_id)
    if versiune is not None:
        q = q.where(VerdictSalvat.versiune == versiune)
    if validator is not None:
        q = q.where(VerdictSalvat.validator == validator)
    return list(db.execute(q.order_by(VerdictSalvat.creat_la, VerdictSalvat.id)).scalars())


def verdicte_rulare(db: Session, rulare_id: uuid.UUID) -> list[VerdictSalvat]:
    return list(
        db.execute(
            select(VerdictSalvat)
            .where(VerdictSalvat.rulare_id == rulare_id)
            .order_by(VerdictSalvat.creat_la, VerdictSalvat.id)
        ).scalars()
    )


def ultima_rulare(db: Session, livrabil_id: uuid.UUID) -> Rulare | None:
    return db.execute(
        select(Rulare)
        .where(Rulare.livrabil_id == livrabil_id)
        .order_by(Rulare.creat_la.desc(), Rulare.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def pentru_ecran(db: Session, livrabil_id: uuid.UUID) -> list[dict[str, Any]]:
    """Rulările cu verdictele lor, pentru urma livrabilului (cele mai noi întâi)."""
    iesire = []
    for r in reversed(rulari(db, livrabil_id)):
        iesire.append({"rulare": r, "verdicte": verdicte_rulare(db, r.id), "decizie": Decizie(r.decizie)})
    return iesire
