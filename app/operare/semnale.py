"""Semnalele de viață ale workerilor (22.3): bătaia de inimă, repornirile după cădere, workerii fără semn.

Fără dependență de motor: se importă ușor (de exemplu de verificarea de sănătate a serviciului `worker`).
Funcțiile primesc o sesiune de agenție (`app.db.sesiune_agentie`); numai `este_viu` își deschide una.
"""

import os
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.db import sesiune_agentie
from app.ids import new_id
from app.operare.tabele import EvenimentWorker, SemnalWorker

EV_PORNIT = "pornit"
EV_OPRIT_CURAT = "oprit_curat"
EV_REPORNIT_DUPA_CADERE = "repornit_dupa_cadere"
EV_FARA_SEMN = "fara_semn_de_viata"
EV_ALERTA_REPORNIRI = "alerta_reporniri"


@dataclass(frozen=True)
class Pornire:
    """Ce s-a aflat la pornirea unui worker."""

    dupa_cadere: bool  # instanța anterioară nu s-a oprit curat
    reporniri_in_fereastra: int  # căderi urmate de repornire, în fereastra dată
    alerta: bool  # s-a atins pragul și nu s-a mai alertat în fereastră


_acum_minus_sec = text("now() - make_interval(secs => :s)")


def _eveniment(db: Session, worker_id: str, tip: str, detalii: dict[str, object] | None = None) -> None:
    db.add(EvenimentWorker(id=new_id(), worker_id=worker_id, tip=tip, detalii=detalii or {}))


def inregistreaza_pornire(
    db: Session, worker_id: str, *, versiune: str, fereastra_min: int, prag: int, pid: int | None = None
) -> Pornire:
    """Înregistrează pornirea. Dacă rândul anterior al acestui worker nu era „oprit curat”, instanța
    dinainte a căzut (SIGKILL, memorie, alimentare): se scrie `repornit_dupa_cadere`. Alertă când în
    fereastră sunt cel puțin `prag` astfel de reporniri (22.3: „la a treia repornire într-o oră”),
    cel mult una pe fereastră."""
    rand = db.get(SemnalWorker, worker_id, with_for_update=True)
    dupa_cadere = rand is not None and not rand.oprit_curat
    mine = pid if pid is not None else os.getpid()
    if rand is None:
        db.add(SemnalWorker(worker_id=worker_id, pid=mine, versiune=versiune))
    else:
        rand.pid, rand.versiune = mine, versiune
        rand.pornit_la = rand.ultimul_semnal = func.now()
        rand.oprit_curat, rand.oprit_la, rand.semnalat_mort = False, None, False
    _eveniment(db, worker_id, EV_PORNIT, {"pid": mine, "versiune": versiune})
    if dupa_cadere:
        _eveniment(
            db,
            worker_id,
            EV_REPORNIT_DUPA_CADERE,
            {"ultimul_semnal": str(rand.ultimul_semnal) if rand else ""},
        )
    db.flush()
    interval = text("now() - make_interval(mins => :m)")
    reporniri = db.execute(
        select(func.count())
        .select_from(EvenimentWorker)
        .where(EvenimentWorker.worker_id == worker_id, EvenimentWorker.tip == EV_REPORNIT_DUPA_CADERE)
        .where(EvenimentWorker.la > interval.bindparams(m=fereastra_min))
    ).scalar_one()
    alerta = False
    if dupa_cadere and reporniri >= prag:
        deja = db.execute(
            select(func.count())
            .select_from(EvenimentWorker)
            .where(EvenimentWorker.worker_id == worker_id, EvenimentWorker.tip == EV_ALERTA_REPORNIRI)
            .where(EvenimentWorker.la > interval.bindparams(m=fereastra_min))
        ).scalar_one()
        alerta = deja == 0
        if alerta:
            _eveniment(
                db, worker_id, EV_ALERTA_REPORNIRI, {"reporniri": reporniri, "fereastra_min": fereastra_min}
            )
    return Pornire(dupa_cadere=dupa_cadere, reporniri_in_fereastra=reporniri, alerta=alerta)


def bate_inima(db: Session, worker_id: str) -> None:
    db.execute(
        update(SemnalWorker).where(SemnalWorker.worker_id == worker_id).values(ultimul_semnal=func.now())
    )


def marcheaza_oprit_curat(db: Session, worker_id: str) -> None:
    db.execute(
        update(SemnalWorker)
        .where(SemnalWorker.worker_id == worker_id)
        .values(oprit_curat=True, oprit_la=func.now(), ultimul_semnal=func.now())
    )
    _eveniment(db, worker_id, EV_OPRIT_CURAT)


def fara_semn_de_viata(db: Session, timeout_sec: float, *, exclus: str) -> list[SemnalWorker]:
    """Workerii (alții decât `exclus`) care nu s-au oprit curat și nu au dat semn de `timeout_sec`,
    încă nesemnalați. Îi marchează ca semnalați (o singură alertă pe cădere) și scrie evenimentul."""
    mort = list(
        db.execute(
            select(SemnalWorker)
            .where(SemnalWorker.worker_id != exclus, SemnalWorker.oprit_curat.is_(False))
            .where(SemnalWorker.semnalat_mort.is_(False))
            .where(
                SemnalWorker.ultimul_semnal
                < text("now() - make_interval(secs => :s)").bindparams(s=timeout_sec)
            )
            .with_for_update(skip_locked=True)
        ).scalars()
    )
    for w in mort:
        w.semnalat_mort = True
        _eveniment(db, w.worker_id, EV_FARA_SEMN, {"ultimul_semnal": w.ultimul_semnal.isoformat()})
    db.flush()
    return mort


def toate(db: Session) -> list[SemnalWorker]:
    return list(db.execute(select(SemnalWorker).order_by(SemnalWorker.worker_id)).scalars())


@dataclass(frozen=True)
class StareWorker:
    worker_id: str
    viu: bool
    oprit_curat: bool
    ultimul_semnal: datetime
    secunde_de_la_semnal: float
    pornit_la: datetime


def stare_workeri(db: Session, timeout_sec: float) -> list[StareWorker]:
    """Starea fiecărui worker cunoscut, calculată de baza de date (același ceas pentru toți)."""
    randuri = db.execute(
        text(
            "SELECT worker_id, oprit_curat, ultimul_semnal, pornit_la, "
            "extract(epoch FROM now() - ultimul_semnal) AS de_cand FROM worker_semnale ORDER BY worker_id"
        )
    ).all()
    return [
        StareWorker(
            worker_id=r.worker_id,
            viu=(not r.oprit_curat) and r.de_cand <= timeout_sec,
            oprit_curat=r.oprit_curat,
            ultimul_semnal=r.ultimul_semnal,
            secunde_de_la_semnal=float(r.de_cand),
            pornit_la=r.pornit_la,
        )
        for r in randuri
    ]


def este_viu(worker_id: str, timeout_sec: float) -> bool:
    """Verificarea de sănătate a serviciului `worker` (compose): semn mai nou decât `timeout_sec`?"""
    with sesiune_agentie() as db:
        return any(w.viu for w in stare_workeri(db, timeout_sec) if w.worker_id == worker_id)


__all__ = ["Pornire", "StareWorker"]
