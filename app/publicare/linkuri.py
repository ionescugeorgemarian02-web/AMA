"""Linkurile semnate ale fișierelor (F9.3, docs/06: „fișierele cerute de Instagram și TikTok se servesc prin
proxy, cu linkuri semnate care expiră”). Platforma aduce fișierul de la adresa publică; linkul spune ce
fișier și până când, semnat cu HMAC (cheie derivată din `AMA_MASTER_KEY`); orice modificare sau expirare dă
404.

    url = linkuri.semneaza("clienti/<id>/video/final.mp4", valabil_sec=3600)
"""

import base64
import datetime as dt
import hmac
import json
from pathlib import Path

from app.config import get_settings
from app.conturi import criptare

PREFIX = "/publicare/fisier/"
VALABIL_IMPLICIT = 6 * 3600  # [I] containerele Instagram expiră în 24 h; descărcarea are loc în minute


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _din_b64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def jeton(cale: str, *, valabil_sec: int = VALABIL_IMPLICIT, acum: dt.datetime | None = None) -> str:
    acum = acum or dt.datetime.now(dt.UTC)
    corp = _b64(
        json.dumps({"c": cale, "e": int(acum.timestamp()) + valabil_sec}, separators=(",", ":")).encode()
    )
    return f"{corp}.{_b64(criptare.hmac_valoare('linkuri-media', corp)[:20])}"


def semneaza(cale: str, *, valabil_sec: int = VALABIL_IMPLICIT, acum: dt.datetime | None = None) -> str:
    """Adresa publică, semnată, a unui fișier din directorul media (cale relativă)."""
    return get_settings().public_url.rstrip("/") + PREFIX + jeton(cale, valabil_sec=valabil_sec, acum=acum)


def verifica(j: str, *, acum: dt.datetime | None = None) -> Path | None:
    """Fișierul de pe disc pentru un jeton valabil, sau `None` (semnătură greșită, expirat, în afara
    directorului)."""
    acum = acum or dt.datetime.now(dt.UTC)
    try:
        corp, semn = j.split(".", 1)
        if not hmac.compare_digest(_din_b64(semn), criptare.hmac_valoare("linkuri-media", corp)[:20]):
            return None
        date = json.loads(_din_b64(corp))
    except (ValueError, KeyError):
        return None
    if int(date["e"]) < acum.timestamp():
        return None
    baza = Path(get_settings().media_dir).resolve()
    cale = (baza / str(date["c"])).resolve()
    return cale if cale.is_relative_to(baza) and cale.is_file() else None
