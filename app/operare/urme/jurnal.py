"""Scrierea urmelor (FT.1): în tranzacția apelantului sau într-una proprie; firul și cauza din context.

Firul: `app.logging.correlation_id` (setat de middleware-ul HTTP, de motor la începutul unui job și de
`corelare`). Cauza: urma-părinte curentă (`span` o setează pentru tot ce se întâmplă în interiorul lui).
"""

import datetime as dt
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import sesiune_agentie
from app.db.motor import CTX_KEY
from app.ids import new_id
from app.logging import correlation_id, get_logger
from app.operare.urme.modele import Urma
from app.operare.urme.rezumat import mascheaza, rezuma_dict

log = get_logger("app.operare.urme")

REZULTATE = ("ok", "esec", "respins", "amanat", "blocat", "info")
UNITATI = ("", "usd_umbra", "lei", "usd")

cauza_curenta: ContextVar[uuid.UUID | None] = ContextVar("urme_cauza", default=None)
tenant_curent: ContextVar[uuid.UUID | None] = ContextVar("urme_tenant", default=None)
actor_curent: ContextVar[str | None] = ContextVar("urme_actor", default=None)


def active() -> bool:
    return get_settings().urme_active


def corelare_curenta() -> str:
    """Firul curent; dacă nu există, unul nou (setat în context, ca urmele următoare să-l împartă)."""
    cid = correlation_id.get()
    if not cid:
        cid = new_id().hex
        correlation_id.set(cid)
    return cid


@contextmanager
def corelare(cid: str | None = None, *, tenant_id: uuid.UUID | None = None) -> Iterator[str]:
    """Pornește (sau continuă, dacă `cid` e dat) un fir; la ieșire contextul revine la cel dinainte."""
    t1 = correlation_id.set(cid or correlation_id.get() or new_id().hex)
    t2 = tenant_curent.set(tenant_id or tenant_curent.get())
    try:
        yield correlation_id.get() or ""
    finally:
        tenant_curent.reset(t2)
        correlation_id.reset(t1)


@dataclass
class _Valori:
    componenta: str
    actiune: str
    rezultat: str = "ok"
    motiv: str = ""
    cod: str = ""
    cost: Decimal = Decimal(0)
    unitate_cost: str = ""
    durata_ms: int | None = None
    intrari: dict[str, Any] = field(default_factory=dict)
    iesiri: dict[str, Any] = field(default_factory=dict)
    obiect_tip: str | None = None
    obiect_id: str | None = None
    actor: str | None = None
    tenant_id: uuid.UUID | None = None
    cauza_id: uuid.UUID | None = None
    corelare_id: str | None = None
    la: dt.datetime | None = None
    id: uuid.UUID | None = None

    def rand(self, ctx_tenant: uuid.UUID | None) -> dict[str, Any]:
        if self.rezultat not in REZULTATE:
            raise ValueError(f"rezultat necunoscut: {self.rezultat!r}")
        if self.unitate_cost not in UNITATI:
            raise ValueError(f"unitate de cost necunoscută: {self.unitate_cost!r}")
        r: dict[str, Any] = {
            "id": self.id or new_id(),
            "tenant_id": self.tenant_id or ctx_tenant or tenant_curent.get(),
            "corelare_id": (self.corelare_id or corelare_curenta())[:100],
            "cauza_id": self.cauza_id or cauza_curenta.get(),
            "componenta": self.componenta[:60],
            "actiune": self.actiune[:120],
            "actor": (self.actor or actor_curent.get() or "sistem")[:100],
            "motiv": mascheaza(self.motiv)[:500],
            "rezultat": self.rezultat,
            "cod": self.cod[:100],
            "cost": max(Decimal(str(self.cost)), Decimal(0)),
            "unitate_cost": self.unitate_cost,
            "durata_ms": None if self.durata_ms is None else max(int(self.durata_ms), 0),
            "obiect_tip": self.obiect_tip,
            "obiect_id": None if self.obiect_id is None else str(self.obiect_id)[:100],
            "intrari": rezuma_dict(self.intrari),
            "iesiri": rezuma_dict(self.iesiri),
        }
        if self.la is not None:
            r["la"] = self.la
        return r


def inregistreaza(db: Session, componenta: str, actiune: str, **kw: Any) -> uuid.UUID | None:
    """O urmă în tranzacția `db` (atomică cu acțiunea), într-un punct de salvare: dacă urma nu se poate scrie,
    acțiunea continuă (se scrie un avertisment). Întoarce id-ul urmei sau None."""
    if not active():
        return None
    try:
        ctx = db.info.get(CTX_KEY)
        rand = _Valori(componenta, actiune, **kw).rand(ctx.tenant_id if ctx else None)
        with db.begin_nested():
            db.execute(insert(Urma).values(**rand))
        return rand["id"]  # type: ignore[no-any-return]
    except Exception as exc:
        log.warning("urma nescrisă", extra={"componenta": componenta, "tip_eroare": type(exc).__name__})
        return None


def emite(componenta: str, actiune: str, **kw: Any) -> uuid.UUID | None:
    """O urmă în tranzacție proprie (scop de agenție), „cel mai bun efort”: nu aruncă niciodată."""
    if not active():
        return None
    try:
        rand = _Valori(componenta, actiune, **kw).rand(None)
        with sesiune_agentie() as db:
            db.execute(insert(Urma).values(**rand))
        return rand["id"]  # type: ignore[no-any-return]
    except Exception as exc:
        log.warning("urma nescrisă", extra={"componenta": componenta, "tip_eroare": type(exc).__name__})
        return None


@dataclass
class Span:
    """Urma unei operații în curs: rezultatul și ieșirile se completează înainte de ieșirea din `span`."""

    id: uuid.UUID
    rezultat: str = "ok"
    motiv: str = ""
    cod: str = ""
    cost: Decimal = Decimal(0)
    unitate_cost: str = ""
    iesiri: dict[str, Any] = field(default_factory=dict)


@contextmanager
def span(componenta: str, actiune: str, *, db: Session | None = None, **kw: Any) -> Iterator[Span]:
    """Măsoară o operație; urmele scrise înăuntru o au drept cauză. Excepția = `esec` (tipul ei în `cod`) și
    trece mai departe. Urma se scrie la ieșire (în `db` dacă e dată, altfel în tranzacție proprie)."""
    s = Span(id=new_id())
    corelare_curenta()
    parinte = cauza_curenta.get()
    jeton = cauza_curenta.set(s.id)
    start = time.monotonic()
    try:
        yield s
    except BaseException as exc:
        s.rezultat, s.cod = "esec", s.cod or type(exc).__name__
        s.motiv = s.motiv or str(exc)[:300]
        raise
    finally:
        cauza_curenta.reset(jeton)
        valori = dict(kw)
        valori.update(
            id=s.id, cauza_id=kw.get("cauza_id", parinte), rezultat=s.rezultat,
            motiv=s.motiv or kw.get("motiv", ""), cod=s.cod, cost=s.cost, unitate_cost=s.unitate_cost,
            iesiri=s.iesiri,
            durata_ms=int((time.monotonic() - start) * 1000),
        )  # fmt: skip
        if db is not None:
            inregistreaza(db, componenta, actiune, **valori)
        else:
            emite(componenta, actiune, **valori)
