"""Jurnalul de apeluri (8.8, 20.4, 22.1): metadate păstrate, conținut păstrat 30 de zile.

Decizia despre conținut: mesajele trimise (după interceptori, deci după mascarea din F3.9) și răspunsul
validat stau în
`gateway_apeluri_continut`, tabel cu `tenant_id`, RLS și `expira_la`; metadatele (model, tokeni, durată,
rezultat,
preț-umbră, traseul încercărilor) stau în `gateway_apeluri` și rămân. Conținutul NU stă în tabelele motorului
(argumentele fluxurilor sunt doar identificatori), nici în jurnalele aplicației (`app/logging`), nici în
audit.

Scrierea se face într-o tranzacție proprie, pe clientul apelului: și un apel care a eșuat, a fost amânat
sau refuzat
lasă urmă, chiar dacă apelantul face rollback. Dacă scrierea însăși eșuează, apelul nu se pierde (modelul
a răspuns
deja): se scrie o eroare în jurnalul aplicației, FĂRĂ conținut.
"""

import datetime as dt
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import sesiune_agentie, sesiune_tenant
from app.gateway import ceas
from app.gateway.modele import Apel, ApelContinut
from app.logging import get_logger

log = get_logger("app.gateway")

REZULTATE = ("ok", "esec", "amanat", "refuzat")


@dataclass(frozen=True)
class IntrareJurnal:
    id: uuid.UUID
    tenant_id: uuid.UUID
    componenta: str
    prioritate: str
    profil: str
    rezultat: str
    livrabil_id: uuid.UUID | None = None
    prompt_nume: str = ""
    prompt_versiune: int | None = None
    furnizor: str = ""
    model: str = ""
    nivel: str = ""
    motiv_alegere: str = ""
    cod_eroare: str = ""
    tokeni_intrare: int = 0
    tokeni_iesire: int = 0
    durata_ms: int = 0
    reparatii: int = 0
    pret_umbra: Decimal = Decimal(0)
    degradat: bool = False
    provizoriu: bool = False
    verificare_suplimentara: bool = False
    incercari: list[dict[str, Any]] = field(default_factory=list)
    corelare_id: str = ""
    mesaje: list[dict[str, str]] = field(default_factory=list)
    raspuns: dict[str, Any] | None = None
    semnale: list[dict[str, Any]] = field(default_factory=list)  # F3.9: date mascate, tentative de injecție


def scrie(intrare: IntrareJurnal) -> bool:
    """Scrie metadatele și conținutul într-o tranzacție proprie. Întoarce `False` (fără excepție) dacă nu
    a reușit."""
    try:
        acum = ceas.acum()
        expira = acum + dt.timedelta(days=get_settings().gateway_continut_zile)
        with sesiune_tenant(intrare.tenant_id) as db:
            db.add(
                Apel(
                    id=intrare.id, tenant_id=intrare.tenant_id, livrabil_id=intrare.livrabil_id,
                    componenta=intrare.componenta[:100], prioritate=intrare.prioritate,
                    profil=intrare.profil[:60],
                    prompt_nume=intrare.prompt_nume[:100], prompt_versiune=intrare.prompt_versiune,
                    furnizor=intrare.furnizor[:40], model=intrare.model[:250], nivel=intrare.nivel,
                    motiv_alegere=intrare.motiv_alegere[:300], rezultat=intrare.rezultat,
                    cod_eroare=intrare.cod_eroare[:100], tokeni_intrare=intrare.tokeni_intrare,
                    tokeni_iesire=intrare.tokeni_iesire, durata_ms=intrare.durata_ms,
                    reparatii=intrare.reparatii,
                    pret_umbra=intrare.pret_umbra, degradat=intrare.degradat, provizoriu=intrare.provizoriu,
                    verificare_suplimentara=intrare.verificare_suplimentara, incercari=intrare.incercari,
                    corelare_id=intrare.corelare_id[:100], creat_la=acum, semnale=intrare.semnale,
                )
            )  # fmt: skip
            db.flush()
            if intrare.mesaje or intrare.raspuns is not None:
                db.add(
                    ApelContinut(
                        apel_id=intrare.id, tenant_id=intrare.tenant_id, mesaje=intrare.mesaje,
                        raspuns=intrare.raspuns, expira_la=expira,
                    )
                )  # fmt: skip
        return True
    except (
        Exception
    ) as exc:  # jurnalul nu are voie să piardă un răspuns deja plătit; nu scriem conținutul în erori
        log.error(
            "jurnalul de apeluri nu s-a putut scrie",
            extra={
                "apel": str(intrare.id),
                "tenant": str(intrare.tenant_id),
                "tip_eroare": type(exc).__name__,
            },
        )
        return False


# --- citire (panou)


@dataclass(frozen=True)
class Filtre:
    client: uuid.UUID | None = None
    model: str = ""
    rezultat: str = ""
    furnizor: str = ""


def _conditii(f: Filtre) -> list[Any]:
    c: list[Any] = []
    if f.client is not None:
        c.append(Apel.tenant_id == f.client)
    if f.model:
        c.append(Apel.model.ilike(f"%{_scapa_like(f.model)}%", escape="\\"))
    if f.furnizor:
        c.append(Apel.furnizor == f.furnizor)
    if f.rezultat in REZULTATE:
        c.append(Apel.rezultat == f.rezultat)
    return c


def _scapa_like(text_: str) -> str:
    return text_.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def lista(db: Session, f: Filtre, *, limita: int = 50, decalaj: int = 0) -> list[Apel]:
    q = (
        select(Apel)
        .where(*_conditii(f))
        .order_by(Apel.creat_la.desc(), Apel.id.desc())
        .limit(limita)
        .offset(decalaj)
    )
    return list(db.execute(q).scalars())


@dataclass(frozen=True)
class Totaluri:
    apeluri: int
    tokeni: int
    pret_umbra: Decimal


def totaluri(db: Session, f: Filtre) -> Totaluri:
    r = db.execute(
        select(
            func.count(Apel.id),
            func.coalesce(func.sum(Apel.tokeni_intrare + Apel.tokeni_iesire), 0),
            func.coalesce(func.sum(Apel.pret_umbra), 0),
        ).where(*_conditii(f))
    ).one()
    return Totaluri(int(r[0]), int(r[1]), Decimal(r[2]))


def citeste(db: Session, apel_id: uuid.UUID) -> tuple[Apel, ApelContinut | None] | None:
    a = db.get(Apel, apel_id)
    if a is None:  # inexistent sau al altui client (RLS)
        return None
    return a, db.get(ApelContinut, apel_id)


def modele_folosite(db: Session) -> list[str]:
    return list(
        db.execute(select(Apel.model).where(Apel.model != "").distinct().order_by(Apel.model)).scalars()
    )


# --- retenție


def curata_continut(*, acum: dt.datetime | None = None) -> int:
    """Șterge conținutul expirat (rămân metadatele). Rulează zilnic, ca proces de agenție (toți clienții)."""
    acum = acum or ceas.acum()
    with sesiune_agentie() as db:
        r = db.execute(text("DELETE FROM gateway_apeluri_continut WHERE expira_la <= :a"), {"a": acum})
        return int(getattr(r, "rowcount", 0) or 0)
