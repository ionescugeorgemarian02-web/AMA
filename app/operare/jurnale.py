"""Partea comună a jurnalelor: context implicit, curățarea detaliilor, scrierea fără RETURNING."""

import uuid
from contextvars import ContextVar
from typing import Any

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.db.motor import CTX_KEY
from app.ids import new_id
from app.logging import correlation_id

# Adresa IP a cererii curente; setată de middleware-ul HTTP. Lipsește în CLI și în joburi.
ip_cerere: ContextVar[str | None] = ContextVar("ip_cerere", default=None)

# Jurnalele nu primesc secrete: orice cheie care conține una dintre aceste părți este refuzată.
PARTI_INTERZISE = (
    "parola",
    "password",
    "secret",
    "token",
    "jeton",
    "cod",
    "code",
    "totp",
    "hash",
    "cheie",
    "key",
)
LUNGIME_MAXIMA_TEXT = 500


class DetaliiNepermise(ValueError):
    pass


def curata_detalii(detalii: dict[str, Any] | None) -> dict[str, Any]:
    """Refuză chei care par secrete (greșeală de programare) și taie textele lungi."""

    def parcurge(valoare: Any, cale: str) -> Any:
        if isinstance(valoare, dict):
            out: dict[str, Any] = {}
            for k, v in valoare.items():
                if any(p in str(k).lower() for p in PARTI_INTERZISE):
                    raise DetaliiNepermise(f"cheie nepermisă în jurnal: {cale}{k!r}")
                out[str(k)] = parcurge(v, f"{cale}{k}.")
            return out
        if isinstance(valoare, list | tuple):
            return [parcurge(v, cale) for v in valoare]
        if isinstance(valoare, uuid.UUID):
            return str(valoare)
        if isinstance(valoare, str):
            return valoare[:LUNGIME_MAXIMA_TEXT]
        if valoare is None or isinstance(valoare, bool | int | float):
            return valoare
        return str(valoare)[:LUNGIME_MAXIMA_TEXT]

    return parcurge(detalii or {}, "")  # type: ignore[no-any-return]


def _context(db: Session) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    ctx = db.info.get(CTX_KEY)
    return (ctx.user_id, ctx.tenant_id) if ctx else (None, None)


# „Ia clientul din contextul sesiunii”. `None` înseamnă explicit „fără client” (intrare la nivel de agenție).
DIN_CONTEXT = "din_context"


def scrie(
    db: Session,
    model: Any,
    valori: dict[str, Any],
    *,
    utilizator_id: uuid.UUID | None,
    tenant_id: uuid.UUID | str | None,
) -> uuid.UUID:
    """Inserează un rând de jurnal în tranzacția curentă. Fără RETURNING: politica de citire e mai strictă."""
    ctx_user, ctx_tenant = _context(db)
    utilizator_id = utilizator_id or ctx_user
    if tenant_id == DIN_CONTEXT:
        tenant_id = ctx_tenant
    rand_id = new_id()
    db.execute(
        insert(model.__table__).values(
            id=rand_id,
            utilizator_id=utilizator_id,
            tenant_id=tenant_id,
            corelare_id=correlation_id.get(),
            **valori,
        )
    )
    return rand_id
