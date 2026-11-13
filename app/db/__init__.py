"""Accesul la baza de date. Orice interogare trece pe aici: sesiunea setează clientul curent (AGENTS.md)."""

from app.db.contexte import ContextDb
from app.db.motor import (
    ContextNepermis,
    get_engine,
    reset_engine,
    restrans_la_client,
    sesiune,
    sesiune_agentie,
    sesiune_anulata,
    sesiune_auth,
    sesiune_tenant,
    verifica_baza,
)

__all__ = [
    "ContextDb",
    "ContextNepermis",
    "get_engine",
    "reset_engine",
    "restrans_la_client",
    "sesiune",
    "sesiune_agentie",
    "sesiune_anulata",
    "sesiune_auth",
    "sesiune_tenant",
    "verifica_baza",
]
