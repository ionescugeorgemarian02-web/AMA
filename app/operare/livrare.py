"""Livrarea, partea din aplicație (contract: docs/specs/F1.8.md, „Contract deployer ↔ aplicație”).

Rutele `/intern/livrare/*` sunt apelate doar de deployer, pe rețeaua internă (proxy-ul răspunde 404 pentru
`/intern/*`). Le păzește jetonul `X-Livrare-Token`. Nu au CSRF (nu sunt apeluri din browser) și nu expun nimic
în afară de cererea curentă și primirea rezultatului.
"""

import hmac
import re
import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import sesiune_agentie
from app.logging import get_logger
from app.operare import audit
from app.operare.tabele import CerereLivrare, Livrare

log = get_logger("app.livrare")

RE_IMAGINE = re.compile(r"^[a-z0-9][a-z0-9._/:-]*@sha256:[0-9a-f]{64}$")
EXPIRARE_CERERE = timedelta(minutes=30)
FINALE = frozenset({"reusita", "esuata", "revenita"})
ACTIVE = ("solicitata", "in_curs")


class EroareLivrare(Exception):
    """Cerere de promovare/revenire care nu se poate face acum; mesajul se arată proprietarului."""


# --- rutele interne ----------------------------------------------------------------------------


def jeton_livrare(x_livrare_token: Annotated[str | None, Header()] = None) -> None:
    s = get_settings()
    if not s.livrare_activa:
        raise HTTPException(status_code=404)  # dezactivat: nu trădăm că ruta există
    asteptat = s.deploy_token.get_secret_value().encode()
    primit = (x_livrare_token or "").encode()
    if not primit or not hmac.compare_digest(primit, asteptat):
        raise HTTPException(status_code=401, detail="Jeton lipsă sau greșit.")


router = APIRouter(
    prefix="/intern/livrare", tags=["intern"], dependencies=[Depends(jeton_livrare)], include_in_schema=False
)


class Verificare(BaseModel):
    nume: Literal["healthz", "readyz"]
    ok: bool


class Raport(BaseModel):
    mediu: Literal["staging", "productie"]
    stare: Literal["in_curs", "reusita", "esuata", "revenita"]
    cerere_id: uuid.UUID | None = None
    imagine: str | None = Field(default=None, max_length=300, pattern=RE_IMAGINE.pattern)
    versiune: str | None = Field(default=None, max_length=64)
    detalii: str = Field(default="", max_length=500)
    verificari: list[Verificare] = Field(default_factory=list, max_length=10)
    momentul: datetime


@router.get("/cerere")
def cerere_curenta(response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    with sesiune_agentie() as db:
        c = db.execute(
            select(CerereLivrare)
            .where(CerereLivrare.stare.in_(ACTIVE))
            .order_by(CerereLivrare.creat_la, CerereLivrare.id)
            .limit(1)
        ).scalar_one_or_none()
        if c is None:
            return {"cerere": None}
        cerere: dict[str, Any] = {"id": str(c.id), "tip": c.tip, "versiune": c.versiune}
        if c.tip == "promovare":
            cerere["imagine"] = c.imagine
        return {"cerere": cerere}


@router.post("/rezultat")
def primeste_rezultat(raport: Raport, response: Response) -> dict[str, bool]:
    response.headers["Cache-Control"] = "no-store"
    with sesiune_agentie() as db:
        inregistreaza(db, raport)
    return {"ok": True}


# --- logica -------------------------------------------------------------------------------------------------


def inregistreaza(db: Session, r: Raport) -> bool:
    """Scrie raportul; False dacă era deja înregistrat (idempotent pe mediu + cerere|imagine + stare)."""
    cheie = str(r.cerere_id) if r.cerere_id else (r.imagine or "")
    inserat = db.execute(
        pg_insert(Livrare)
        .values(
            id=uuid.uuid4(),
            mediu=r.mediu,
            cheie=cheie,
            cerere_id=r.cerere_id,
            imagine=r.imagine,
            versiune=r.versiune,
            stare=r.stare,
            detalii=r.detalii,
            verificari=[v.model_dump() for v in r.verificari],
            momentul=r.momentul,
        )
        .on_conflict_do_nothing(index_elements=["mediu", "cheie", "stare"])
        .returning(Livrare.id)
    ).first()
    if inserat is None:
        return False
    if r.mediu == "productie" and r.cerere_id:
        _avanseaza_cerere(db, r)
    audit.record(
        db,
        "livrare.raport",
        obiect_tip="livrare",
        obiect_id=r.cerere_id or r.imagine,
        actor_tip="sistem",
        detalii={"mediu": r.mediu, "stare": r.stare, "versiune": r.versiune},
    )
    return True


def _avanseaza_cerere(db: Session, r: Raport) -> None:
    """Tranziții doar înainte: solicitata → in_curs → stare finală; o stare finală nu se mai schimbă."""
    c = db.get(CerereLivrare, r.cerere_id)
    if c is None or c.stare in FINALE:
        return
    if r.stare == "in_curs" and c.stare != "solicitata":
        return
    c.stare, c.detalii = r.stare, r.detalii
    db.execute(
        CerereLivrare.__table__.update()  # type: ignore[attr-defined]
        .where(CerereLivrare.id == c.id)
        .values(actualizat_la=func.clock_timestamp())
    )


# --- starea pentru panou -----------------------------------------------------------------------


class Versiune(BaseModel):
    imagine: str
    versiune: str | None = None
    moment: datetime


class StareLivrare(BaseModel):
    productie: Versiune | None = None
    anterioara: Versiune | None = None
    disponibila: Versiune | None = None  # pe staging, `reusita`, încă nepromovată
    cerere_activa: dict[str, Any] | None = None
    istoric: list[dict[str, Any]] = []


def _versiune(rand: Livrare | None) -> Versiune | None:
    if rand is None or rand.imagine is None:
        return None
    return Versiune(imagine=rand.imagine, versiune=rand.versiune, moment=rand.momentul)


def _expira_cereri_vechi(db: Session) -> None:
    prag = func.clock_timestamp()
    for c in db.execute(
        select(CerereLivrare).where(
            CerereLivrare.stare == "solicitata", CerereLivrare.creat_la < prag - EXPIRARE_CERERE
        )
    ).scalars():
        c.stare, c.detalii = "esuata", "expirată: deployer-ul nu a preluat cererea"


def citeste_stare(db: Session, *, istoric: int = 15) -> StareLivrare:
    prod = list(
        db.execute(
            select(Livrare)
            .where(
                Livrare.mediu == "productie",
                Livrare.stare.in_(("reusita", "revenita")),
                Livrare.imagine.isnot(None),
            )
            .order_by(Livrare.creat_la.desc(), Livrare.id.desc())
            .limit(20)
        ).scalars()
    )
    curenta = prod[0] if prod else None
    anterioara = next((p for p in prod[1:] if curenta and p.imagine != curenta.imagine), None)
    staging = db.execute(
        select(Livrare)
        .where(Livrare.mediu == "staging", Livrare.stare == "reusita", Livrare.imagine.isnot(None))
        .order_by(Livrare.creat_la.desc(), Livrare.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    activa = db.execute(
        select(CerereLivrare).where(CerereLivrare.stare.in_(ACTIVE)).order_by(CerereLivrare.creat_la).limit(1)
    ).scalar_one_or_none()
    disponibila = (
        _versiune(staging)
        if staging and not activa and (curenta is None or staging.imagine != curenta.imagine)
        else None
    )
    rows = db.execute(
        select(Livrare).order_by(Livrare.creat_la.desc(), Livrare.id.desc()).limit(istoric)
    ).scalars()
    return StareLivrare(
        productie=_versiune(curenta),
        anterioara=_versiune(anterioara),
        disponibila=disponibila,
        cerere_activa=None
        if activa is None
        else {"tip": activa.tip, "stare": activa.stare, "versiune": activa.versiune},
        istoric=[
            {
                "mediu": x.mediu,
                "stare": x.stare,
                "versiune": x.versiune,
                "imagine": x.imagine,
                "detalii": x.detalii,
                "moment": x.momentul,
            }
            for x in rows
        ],
    )


def _cere(
    db: Session,
    tip: Literal["promovare", "revenire"],
    imagine: str | None,
    versiune: str | None,
    user: uuid.UUID,
) -> CerereLivrare:
    c = CerereLivrare(tip=tip, imagine=imagine, versiune=versiune, solicitat_de=user)
    db.add(c)
    db.flush()
    audit.record(
        db,
        f"livrare.{tip}_ceruta",
        obiect_tip="cerere_livrare",
        obiect_id=c.id,
        utilizator_id=user,
        detalii={"versiune": versiune, "imagine": imagine},
    )
    return c


def cere_promovare(db: Session, user: uuid.UUID) -> CerereLivrare:
    _expira_cereri_vechi(db)
    stare = citeste_stare(db, istoric=1)
    if stare.cerere_activa:
        raise EroareLivrare("O cerere de livrare este deja în curs.")
    d = stare.disponibila
    if d is None or not RE_IMAGINE.match(d.imagine):
        raise EroareLivrare("Nu există o versiune de pe staging care poate fi promovată.")
    return _cere(db, "promovare", d.imagine, d.versiune, user)


def cere_revenire(db: Session, user: uuid.UUID) -> CerereLivrare:
    _expira_cereri_vechi(db)
    stare = citeste_stare(db, istoric=1)
    if stare.cerere_activa:
        raise EroareLivrare("O cerere de livrare este deja în curs.")
    if stare.anterioara is None:
        raise EroareLivrare("Nu se cunoaște o versiune anterioară la care să se revină.")
    return _cere(db, "revenire", None, stare.anterioara.versiune, user)
