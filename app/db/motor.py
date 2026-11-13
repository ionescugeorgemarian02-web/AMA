"""Motorul și sesiunile. Singura cale spre bază: fiecare sesiune poartă un context de client."""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from uuid import UUID

from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.orm import Session, SessionTransaction

from app.config import get_settings
from app.db.contexte import ContextDb

CTX_KEY = "ama_ctx"

_engine: Engine | None = None

_SET_CONTEXT = text(
    "SELECT set_config('app.tenant_id', :tenant, true), set_config('app.user_id', :utilizator, true),"
    " set_config('app.agency', :agentie, true), set_config('app.auth', :auth, true)"
)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=10, max_overflow=5)
    return _engine


def reset_engine() -> None:
    """Închide motorul (teste, schimbare de configurare)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


def _aplica_context(session: Session, transaction: SessionTransaction, connection: Connection) -> None:
    ctx: ContextDb = session.info[CTX_KEY]
    s = ctx.settings()
    connection.execute(
        _SET_CONTEXT,
        {
            "tenant": s["app.tenant_id"],
            "utilizator": s["app.user_id"],
            "agentie": s["app.agency"],
            "auth": s["app.auth"],
        },
    )


@contextmanager
def sesiune(ctx: ContextDb | None = None) -> Iterator[Session]:
    """Deschide o tranzacție cu contextul dat. Commit la ieșire, rollback la excepție.

    Contextul se reaplică la începutul oricărei tranzacții noi a aceleiași sesiuni; este local tranzacției,
    deci nu rămâne pe conexiunea întoarsă în pool.
    """
    session = Session(get_engine(), expire_on_commit=False)
    session.info[CTX_KEY] = ctx or ContextDb()
    event.listen(session, "after_begin", _aplica_context)
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


class ContextNepermis(RuntimeError):
    """Restrângerea la un client cere o sesiune cu scop de agenție (doar se îngustează, nu se lărgește)."""


@contextmanager
def restrans_la_client(session: Session, tenant_id: UUID, user_id: UUID | None = None) -> Iterator[Session]:
    """ÎNGUSTEAZĂ temporar o sesiune de agenție la un singur client, într-un punct de salvare care se
    ANULEAZĂ la ieșire.

    În interior, politicile RLS se aplică exact ca pentru o sesiune a clientului (fără scop de agenție).
    La ieșire
    punctul de salvare se anulează: tot ce s-a scris înăuntru dispare, iar contextul revine la cel de
    agenție (în
    Postgres, `set_config(..., true)` dintr-un punct de salvare anulat se anulează și el). Nu există drum
    invers:
    dintr-o sesiune de client nu se poate cere scop de agenție. Pentru rulările de probă (bancul de evaluare).
    """
    anterior: ContextDb = session.info[CTX_KEY]
    if not anterior.agency or anterior.auth:
        raise ContextNepermis("restrângerea la un client pornește doar dintr-o sesiune de agenție")
    ingust = ContextDb(tenant_id=tenant_id, user_id=user_id or anterior.user_id)
    punct = session.begin_nested()
    session.info[CTX_KEY] = ingust
    try:
        s = ingust.settings()
        session.execute(
            _SET_CONTEXT,
            {"tenant": s["app.tenant_id"], "utilizator": s["app.user_id"], "agentie": "", "auth": ""},
        )
        yield session
    finally:
        session.info[CTX_KEY] = anterior
        if punct.is_active:
            punct.rollback()


@contextmanager
def sesiune_anulata(ctx: ContextDb | None = None) -> Iterator[Session]:
    """Ca `sesiune`, dar tranzacția se ANULEAZĂ întotdeauna (nimic nu rămâne în bază). Pentru rulările de
    probă; apelantul nu trebuie să cheme `commit`."""
    session = Session(get_engine(), expire_on_commit=False)
    session.info[CTX_KEY] = ctx or ContextDb()
    event.listen(session, "after_begin", _aplica_context)
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def sesiune_tenant(tenant_id: UUID, user_id: UUID | None = None) -> AbstractContextManager[Session]:
    return sesiune(ContextDb(tenant_id=tenant_id, user_id=user_id))


def sesiune_agentie(
    user_id: UUID | None = None, tenant_id: UUID | None = None
) -> AbstractContextManager[Session]:
    return sesiune(ContextDb(tenant_id=tenant_id, user_id=user_id, agency=True))


def sesiune_auth() -> AbstractContextManager[Session]:
    """Doar pentru fluxul de autentificare (căutarea utilizatorului/sesiunii înainte de context)."""
    return sesiune(ContextDb(auth=True))


def verifica_baza() -> None:
    """Verificarea pentru /readyz: aruncă dacă baza nu răspunde."""
    with sesiune() as s:
        s.execute(text("SELECT 1"))
