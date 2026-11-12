"""Indexarea documentelor în pasaje cu vectori (F4.3). Serviciul pașilor fluxului `creier.indexeaza_sursa`.

Doi pași, ambii idempotenți: (1) `pregateste_sursa` taie documentele noi sau schimbate în pasaje (fără vector)
și scoate pasajele documentelor care s-au schimbat; (2) `vectorizeaza_lot` vectorizează cel mult `LOT_VECTORI`
pasaje care nu au vector sau au un vector de la ALT model decât cel activ acum (reindexare la schimbarea
modelului). Vectorii se cer prin `gateway.vectorizeaza_cu_model`; `Amanat` (niciun model activ, server căzut)
iese neprins, ca fluxul să se reprogrameze. Textele clientului merg doar la serverul de vectori propriu
(docs/10 §10.5).
"""

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import gateway
from app.cercetare import Document
from app.config import get_settings
from app.creier import pasaje as nucleu
from app.creier.modele import Pasaj
from app.db import sesiune_tenant
from app.ids import new_id
from app.operare.motor import Prioritate

LOT_VECTORI = 32
COMPONENTA = "creier.indexare"
PAUZA_FARA_MODEL_SEC = 300


class DimensiuneNepotrivita(RuntimeError):
    """Vectorii modelului activ nu au dimensiunea coloanei `pasaje.embedding` (o schimbă o migrare)."""


@dataclass(frozen=True)
class Parametri:
    tinta: int = nucleu.TINTA
    maxim: int = nucleu.MAXIM
    suprapunere: int = nucleu.SUPRAPUNERE


def dimensiune_coloana(db: Session) -> int:
    """Dimensiunea coloanei de vectori, din catalogul bazei."""
    interogare = (
        "SELECT atttypmod FROM pg_attribute WHERE attrelid = 'pasaje'::regclass AND attname = 'embedding'"
    )
    return int(db.execute(text(interogare)).scalar_one())


def pregateste_document(
    db: Session, d: Document, *, parametri: Parametri | None = None, compartiment: str | None = None
) -> int:
    """Pasajele unui document. Dacă există deja pasaje pentru textul lui curent nu face nimic (0). Altfel
    scoate pasajele vechi ale documentului și le inserează pe cele noi, fără vector. Întoarce numărul de
    pasaje noi."""
    p = parametri or Parametri()
    existente = db.execute(
        select(func.count())
        .select_from(Pasaj)
        .where(Pasaj.document_id == d.id, Pasaj.hash_document == d.hash_text)
    ).scalar_one()
    if existente:
        return 0
    db.execute(delete(Pasaj).where(Pasaj.document_id == d.id))
    bucati = nucleu.imparte(d.text, tinta=p.tinta, maxim=p.maxim, suprapunere=p.suprapunere)
    for b in bucati:
        db.add(
            Pasaj(
                id=new_id(),
                tenant_id=d.tenant_id,
                sursa_id=d.sursa_id,
                document_id=d.id,
                pozitie=b.pozitie,
                car_inceput=b.inceput,
                car_sfarsit=b.sfarsit,
                text=b.text,
                text_normalizat=nucleu.normalizeaza(b.text),
                hash_document=d.hash_text,
                compartiment=compartiment,
            )
        )
    db.flush()
    return len(bucati)


def pregateste_sursa(
    db: Session,
    sursa_id: uuid.UUID,
    *,
    parametri: Parametri | None = None,
    compartiment: str | None = None,
) -> int:
    """Taie toate documentele sursei care nu au (încă) pasaje pentru textul lor curent."""
    total = 0
    documente = db.execute(select(Document).where(Document.sursa_id == sursa_id).order_by(Document.id))
    for d in documente.scalars():
        total += pregateste_document(db, d, parametri=parametri, compartiment=compartiment)
    return total


def _de_vectorizat(model: str | None) -> ColumnElement[bool]:
    fara_vector = Pasaj.model_vectori.is_(None)
    return fara_vector if model is None else fara_vector | (Pasaj.model_vectori != model)


def numara_de_vectorizat(db: Session, tenant_id: uuid.UUID, sursa_id: uuid.UUID | None = None) -> int:
    """Pasajele fără vector sau cu vector de la alt model decât cel activ acum."""
    m = gateway.model_vectori(tenant_id)
    q = select(func.count()).select_from(Pasaj)
    q = q.where(Pasaj.tenant_id == tenant_id, _de_vectorizat(m.cod if m else None))
    if sursa_id is not None:
        q = q.where(Pasaj.sursa_id == sursa_id)
    return int(db.execute(q).scalar_one())


def surse_de_vectorizat(db: Session, tenant_id: uuid.UUID) -> list[uuid.UUID]:
    m = gateway.model_vectori(tenant_id)
    q = select(Pasaj.sursa_id).where(Pasaj.tenant_id == tenant_id, _de_vectorizat(m.cod if m else None))
    return list(db.execute(q.distinct().order_by(Pasaj.sursa_id)).scalars())


def vector_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


def vectorizeaza_lot(tenant_id: uuid.UUID, sursa_id: uuid.UUID) -> int:
    """Vectorizează un lot de pasaje ale sursei. Întoarce câte a vectorizat (0 = nimic de făcut). Ridică
    `gateway.Amanat` când nu se poate acum; apelantul reprogramează."""
    model = gateway.model_vectori(tenant_id)
    if model is None:
        pana = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=PAUZA_FARA_MODEL_SEC)
        raise gateway.Amanat(pana, "niciun model de vectori activ")
    with sesiune_tenant(tenant_id) as db:
        lot = list(
            db.execute(
                select(Pasaj.id, Pasaj.text)
                .where(Pasaj.tenant_id == tenant_id, Pasaj.sursa_id == sursa_id, _de_vectorizat(model.cod))
                .order_by(Pasaj.document_id, Pasaj.pozitie)
                .limit(LOT_VECTORI)
            ).all()
        )
        dim = dimensiune_coloana(db)
    if not lot:
        return 0
    if model.dimensiune != dim:
        raise DimensiuneNepotrivita(f"modelul dă vectori de {model.dimensiune}, coloana are {dim}")
    prefix = get_settings().vectori_prefix_pasaj
    vectori, cod_model = gateway.vectorizeaza_cu_model(
        [prefix + t for _, t in lot], tenant_id=tenant_id, componenta=COMPONENTA, prioritate=Prioritate.P3
    )
    actualizare = text(
        "UPDATE pasaje SET embedding = CAST(:e AS vector), model_vectori = :m, vectorizat_la = now() "
        "WHERE id = :i AND tenant_id = :t"
    )
    with sesiune_tenant(tenant_id) as db:
        try:
            for (pid, _), v in zip(lot, vectori, strict=True):
                db.execute(actualizare, {"e": vector_literal(v), "m": cod_model, "i": pid, "t": tenant_id})
        except DBAPIError as exc:
            raise DimensiuneNepotrivita(str(exc.orig)[:200]) from None
    return len(lot)


@dataclass(frozen=True)
class StareIndexare:
    documente: int
    pasaje: int
    vectorizate: int  # cu vectorul modelului activ acum
    de_vectorizat: int
    model_activ: str | None
    modele_in_pasaje: dict[str, int]  # câte pasaje are fiecare model ("" = fără vector)


def stare(db: Session, tenant_id: uuid.UUID, sursa_id: uuid.UUID) -> StareIndexare:
    m = gateway.model_vectori(tenant_id)
    coloana = func.coalesce(Pasaj.model_vectori, "")
    n = {
        str(k): int(v)
        for k, v in db.execute(
            select(coloana, func.count()).where(Pasaj.sursa_id == sursa_id).group_by(coloana)
        ).all()
    }
    total = sum(n.values())
    curente = n.get(m.cod, 0) if m else 0
    documente = db.execute(select(func.count()).select_from(Document).where(Document.sursa_id == sursa_id))
    return StareIndexare(
        documente=int(documente.scalar_one()),
        pasaje=total,
        vectorizate=curente,
        de_vectorizat=total - curente,
        model_activ=m.cod if m else None,
        modele_in_pasaje=n,
    )
