"""Accesul la baza de date. Orice interogare trece pe aici: sesiunea setează clientul curent (AGENTS.md)."""

from app.db.contexte import ContextDb
from app.db.motor import (
    get_engine,
    reset_engine,
    sesiune,
    sesiune_agentie,
    sesiune_auth,
    sesiune_tenant,
    verifica_baza,
)

__all__ = [
    "ContextDb",
    "get_engine",
    "reset_engine",
    "sesiune",
    "sesiune_agentie",
    "sesiune_auth",
    "sesiune_tenant",
    "verifica_baza",
]
