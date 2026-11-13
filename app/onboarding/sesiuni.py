"""Sesiunea de interviu (F4.4): persistentă, reluabilă, cu întrebări de clarificare limitate ca număr.

Serviciul lucrează cu o sesiune de bază primită de la apelant (operatorul completează pentru client în panou;
portalul clientului, F7, va folosi aceleași funcții). Funcțiile NU fac commit: îl face apelantul.

    s = sesiuni.deschide(db, tenant_id=t, utilizator_id=u)          # o singură sesiune deschisă pe client
    q = sesiuni.urmatoarea(db, s.id)                                 # următoarea întrebare fără răspuns
    r = sesiuni.raspunde(db, s.id, q.id, "…", utilizator_id=u)       # r.clarificare: întrebarea nouă sau None
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ids import new_id
from app.onboarding import clarificare, interviu, prompturi
from app.onboarding.modele import IntrebareSesiune, Sesiune
from app.operare import audit

PAS_ORDINE = 100


class EroareOnboarding(Exception):
    pass


class SesiuneInchisa(EroareOnboarding):
    """Interviul nu mai primește răspunsuri (brieful e deja compus sau trimis)."""


@dataclass(frozen=True)
class Rezultat:
    intrebare_id: uuid.UUID
    clarificare: IntrebareSesiune | None
    motiv: str = ""


@dataclass(frozen=True)
class Progres:
    total: int  # întrebările din interviu (fără clarificări)
    raspunse: int
    clarificari_puse: int
    clarificari_deschise: int
    terminat: bool

    @property
    def procent(self) -> int:
        return round(100 * self.raspunse / self.total) if self.total else 0


def sesiune(db: Session, sesiune_id: uuid.UUID) -> Sesiune:
    s = db.get(Sesiune, sesiune_id)
    if s is None:  # inexistentă sau a altui client (RLS)
        raise EroareOnboarding(f"sesiune necunoscută: {sesiune_id}")
    return s


def sesiune_deschisa(db: Session, tenant_id: uuid.UUID) -> Sesiune | None:
    return db.execute(
        select(Sesiune).where(Sesiune.tenant_id == tenant_id, Sesiune.stare != "trimis")
    ).scalar_one_or_none()


def deschide(db: Session, *, tenant_id: uuid.UUID, utilizator_id: uuid.UUID | None) -> Sesiune:
    """Sesiunea deschisă a clientului sau una nouă cu toate întrebările interviului (reluare de unde a
    rămas)."""
    existenta = sesiune_deschisa(db, tenant_id)
    if existenta is not None:
        return existenta
    s = Sesiune(id=new_id(), tenant_id=tenant_id, creat_de=utilizator_id, stare="interviu")
    db.add(s)
    db.flush()
    for k, q in enumerate(interviu.intrebari(), 1):
        db.add(
            IntrebareSesiune(
                id=new_id(), tenant_id=tenant_id, sesiune_id=s.id, ordine=k * PAS_ORDINE, tip="intrebare",
                cod=q.cod, camp=q.camp, text_intrebare=q.text, generata_de="date",
            )
        )  # fmt: skip
    db.flush()
    audit.record(
        db, "onboarding.sesiune_deschisa", obiect_tip="onboarding_sesiune", obiect_id=s.id,
        utilizator_id=utilizator_id, tenant_id=tenant_id,
    )  # fmt: skip
    return s


def intrebari(db: Session, sesiune_id: uuid.UUID) -> list[IntrebareSesiune]:
    return list(
        db.execute(
            select(IntrebareSesiune)
            .where(IntrebareSesiune.sesiune_id == sesiune_id)
            .order_by(IntrebareSesiune.ordine)
        ).scalars()
    )


def urmatoarea(db: Session, sesiune_id: uuid.UUID) -> IntrebareSesiune | None:
    """Prima întrebare (sau clarificare) fără răspuns, în ordinea interviului."""
    return db.execute(
        select(IntrebareSesiune)
        .where(IntrebareSesiune.sesiune_id == sesiune_id, IntrebareSesiune.raspuns.is_(None))
        .order_by(IntrebareSesiune.ordine)
        .limit(1)
    ).scalar_one_or_none()


def progres(db: Session, sesiune_id: uuid.UUID) -> Progres:
    rows = intrebari(db, sesiune_id)
    principale = [r for r in rows if r.tip == "intrebare"]
    clar = [r for r in rows if r.tip == "clarificare"]
    deschise = sum(1 for r in rows if r.raspuns is None)
    return Progres(
        total=len(principale),
        raspunse=sum(1 for r in principale if r.raspuns is not None),
        clarificari_puse=len(clar),
        clarificari_deschise=sum(1 for r in clar if r.raspuns is None),
        terminat=deschise == 0,
    )


def _grup(rows: list[IntrebareSesiune], principala: IntrebareSesiune) -> list[IntrebareSesiune]:
    return [r for r in rows if r.id == principala.id or r.parinte_id == principala.id]


def raspunsuri_pe_camp(db: Session, sesiune_id: uuid.UUID) -> dict[str, list[IntrebareSesiune]]:
    """Rândurile cu răspuns, grupate pe câmpul brieful, în ordine (întrebarea, apoi clarificările ei)."""
    grupat: dict[str, list[IntrebareSesiune]] = {}
    for r in intrebari(db, sesiune_id):
        if r.raspuns is not None:
            grupat.setdefault(r.camp, []).append(r)
    return grupat


def raspunde(
    db: Session,
    sesiune_id: uuid.UUID,
    intrebare_id: uuid.UUID,
    raspuns: str,
    *,
    utilizator_id: uuid.UUID | None,
    cu_clarificari: bool = True,
    acum: dt.datetime | None = None,
) -> Rezultat:
    """Salvează răspunsul. La primul răspuns la o întrebare, dacă e vag, se generează (prin gateway) o
    întrebare
    de clarificare, cel mult `MAX_PE_INTREBARE` pe întrebare și `MAX_PE_SESIUNE` pe sesiune."""
    s = sesiune(db, sesiune_id)
    if s.stare != "interviu":
        raise SesiuneInchisa("interviul nu mai primește răspunsuri: brieful a fost compus")
    q = db.get(IntrebareSesiune, intrebare_id)
    if q is None or q.sesiune_id != sesiune_id:
        raise EroareOnboarding("întrebare necunoscută în această sesiune")
    text = raspuns.strip()
    if not text:
        raise EroareOnboarding("răspunsul este gol")
    if len(text) > 6000:
        raise EroareOnboarding("răspunsul depășește 6000 de caractere")
    prima = q.raspuns is None
    ora = acum or dt.datetime.now(dt.UTC)
    q.raspuns, q.raspuns_la, q.raspuns_de = text, ora, utilizator_id
    s.actualizat_la = ora
    db.flush()
    audit.record(
        db, "onboarding.raspuns", obiect_tip="onboarding_intrebare", obiect_id=q.id,
        utilizator_id=utilizator_id, tenant_id=s.tenant_id, detalii={"intrebare": q.cod, "camp": q.camp},
    )  # fmt: skip
    if not (prima and cu_clarificari):
        return Rezultat(q.id, None, "răspuns salvat")
    toate = intrebari(db, sesiune_id)
    principala = q if q.tip == "intrebare" else next(r for r in toate if r.id == q.parinte_id)
    grup = _grup(toate, principala)
    puse_in_grup = sum(1 for r in grup if r.tip == "clarificare")
    puse_in_sesiune = sum(1 for r in toate if r.tip == "clarificare")
    if puse_in_grup >= clarificare.MAX_PE_INTREBARE or puse_in_sesiune >= clarificare.MAX_PE_SESIUNE:
        return Rezultat(q.id, None, "limita de clarificări atinsă")
    intr = interviu.camp_intrebare(principala.cod)
    agregat = "\n".join(r.raspuns or "" for r in grup if r.raspuns)
    prompturi.asigura()
    v = clarificare.evalueaza(db, tenant_id=s.tenant_id, intrebare=intr, raspuns=agregat)
    if v.suficient:
        return Rezultat(q.id, None, "răspuns suficient")
    ultima = max(r.ordine for r in grup)
    c = IntrebareSesiune(
        id=new_id(), tenant_id=s.tenant_id, sesiune_id=sesiune_id, ordine=ultima + 1, tip="clarificare",
        cod=principala.cod, camp=principala.camp, text_intrebare=v.intrebare, parinte_id=principala.id,
        generata_de=v.generata_de,
    )  # fmt: skip
    db.add(c)
    db.flush()
    return Rezultat(q.id, c, v.lipseste or "răspuns vag")


def starea(db: Session, sesiune_id: uuid.UUID) -> dict[str, Any]:
    s = sesiune(db, sesiune_id)
    return {"stare": s.stare, "progres": progres(db, sesiune_id), "urmatoarea": urmatoarea(db, sesiune_id)}


_ = func
