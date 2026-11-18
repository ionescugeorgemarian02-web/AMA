"""Localizarea în a doua limbă (F16.3): engleza, pentru interfață, conținut și regulile de validare.

    from app import localizare
    localizare.traduce("Aprobări", "en")              # „Approvals” (din `date/en.toml`); necunoscut =
    originalul
    localizare.din_cerere(request)                     # cookie-ul `ama_limba`, apoi Accept-Language,
    apoi „ro”
    localizare.limba_client(db, tenant_id)             # limba conținutului clientului (`clienti.limba`)

Româna rămâne limba de bază: textele din cod și din șabloane sunt în română, iar catalogul spune cum se
afișează
în engleză. Ce lipsește din catalog se afișează în română (nu se ghicește o traducere).
"""

import tomllib
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import Request
from jinja2 import pass_context
from sqlalchemy import text
from sqlalchemy.orm import Session

LIMBI = {"ro": "Română", "en": "English"}
IMPLICITA = "ro"
COOKIE = "ama_limba"
DATE = Path(__file__).parent / "date"


def normalizeaza(cod: str | None) -> str:
    c = (cod or "").strip().lower()[:2]
    return c if c in LIMBI else IMPLICITA


@lru_cache(maxsize=4)
def _catalog(limba: str) -> dict[str, Any]:
    f = DATE / f"{limba}.toml"
    return tomllib.loads(f.read_text()) if f.exists() else {}


def catalog(limba: str) -> dict[str, str]:
    return dict(_catalog(limba).get("interfata", {}))


def traduce(sursa: str, limba: str) -> str:
    """Textul de interfață în limba cerută; în română sau fără traducere: textul însuși."""
    if limba == IMPLICITA:
        return sursa
    return catalog(limba).get(sursa, sursa)


def lipsa(texte: list[str], limba: str) -> list[str]:
    """Textele fără traducere (testul catalogului)."""
    c = catalog(limba)
    return [x for x in texte if x not in c]


def din_cerere(request: Request) -> str:
    """Limba interfeței: alegerea salvată (cookie), apoi prima limbă cunoscută din Accept-Language."""
    ales = request.cookies.get(COOKIE)
    if ales in LIMBI:
        return str(ales)
    for parte in request.headers.get("accept-language", "").split(","):
        cod = parte.split(";")[0].strip().lower()[:2]
        if cod in LIMBI:
            return cod
    return IMPLICITA


@pass_context
def t_jinja(ctx: Any, sursa: str) -> str:
    """`{{ t("Aprobări") }}` în șabloane: limba vine din contextul paginii (`limba`)."""
    return traduce(sursa, normalizeaza(ctx.get("limba")))


# --- conținutul -------------------------------------------------------------------------------------------


def limba_client(db: Session, tenant_id: uuid.UUID) -> str:
    """Limba în care se scrie conținutul clientului (`clienti.limba`, migrarea 0105)."""
    v = db.execute(text("SELECT limba FROM clienti WHERE id = :t"), {"t": tenant_id}).scalar_one_or_none()
    return normalizeaza(v)


def seteaza_limba_client(db: Session, tenant_id: uuid.UUID, limba: str) -> None:
    if limba not in LIMBI:
        raise ValueError(f"limbă necunoscută: {limba}")
    db.execute(text("UPDATE clienti SET limba = :l WHERE id = :t"), {"l": limba, "t": tenant_id})


def instructiune_continut(limba: str) -> str:
    """Blocul adăugat în contextul autorilor (F6) pentru un client care publică în altă limbă."""
    if limba == IMPLICITA:
        return ""
    return str(_catalog(limba).get("continut", {}).get("instructiune", ""))


def adaos_context(db: Session, lv: Any) -> str:
    """Punctul de extensie `continut.scriere.inregistreaza_adaos_context`."""
    return instructiune_continut(limba_client(db, lv.tenant_id))


__all__ = [
    "COOKIE",
    "IMPLICITA",
    "LIMBI",
    "adaos_context",
    "catalog",
    "din_cerere",
    "instructiune_continut",
    "limba_client",
    "lipsa",
    "normalizeaza",
    "seteaza_limba_client",
    "t_jinja",
    "traduce",
]
