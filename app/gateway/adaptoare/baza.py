"""Contractul unui adaptor și clasificarea comună a erorilor HTTP (7.5).

Un adaptor știe doar două lucruri: cum arată cererea către API-ul lui și cum se citește răspunsul.
Retrimiterea,
limitele și alegerea modelului sunt ale gateway-ului. Un adaptor nu citește cheia din mediu (primește antetul
gata făcut de la client) și nu scrie nimic în jurnale.
"""

import datetime as dt
import json
from typing import Any, ClassVar, Protocol

import httpx

from app.gateway import antete as antete_limita
from app.gateway.erori import EroareFurnizor
from app.gateway.tipuri import AntetLimita, CerereModel, Destinatie, RaspunsModel

DETALIU_MAXIM = 120


class Adaptor(Protocol):
    """Interfața adaptoarelor. Se înregistrează cu `adaptoare.inregistreaza` (punct de extensie pentru
    F3.5)."""

    tip_api: ClassVar[str]

    def cerere(self, dest: Destinatie, cheie: str | None, cerere: CerereModel) -> httpx.Request: ...

    def raspuns(self, raspuns: httpx.Response, acum: dt.datetime) -> RaspunsModel: ...


def json_sau_gol(r: httpx.Response) -> Any:
    try:
        return r.json()
    except ValueError:
        return None


def cod_eroare(corp: Any) -> str:
    """Un cod scurt din corpul unei erori (`type` / `code` / `status`), niciodată `message`: mesajul poate
    repeta
    promptul sau cheia."""
    if not isinstance(corp, dict):
        return ""
    e = corp.get("error", corp)
    if isinstance(e, dict):
        for k in ("type", "code", "status"):
            v = e.get(k)
            if isinstance(v, str | int) and not isinstance(v, bool):
                return str(v)[:DETALIU_MAXIM]
    return ""


def clasifica(r: httpx.Response, corp: Any, acum: dt.datetime) -> EroareFurnizor:
    """Statusul și antetele unui răspuns de eroare → eroarea tipizată, cu timpul de așteptare când îl știm."""
    ant = antete_limita.citeste(r.headers, acum)
    detaliu = cod_eroare(corp)
    s = r.status_code
    if s == 429:
        return EroareFurnizor("limita", status=s, detaliu=detaliu, retry_dupa=_pauza_429(ant, corp, acum))
    if s in (401, 403):
        return EroareFurnizor("autentificare", status=s, detaliu=detaliu)
    if s == 408 or s >= 500:  # inclusiv 529 „supraîncărcat” (Anthropic)
        return EroareFurnizor("server", status=s, detaliu=detaliu, retry_dupa=ant.retry_dupa_sec)
    return EroareFurnizor("cerere", status=s, detaliu=detaliu)


def _pauza_429(ant: AntetLimita, corp: Any, acum: dt.datetime) -> float | None:
    if ant.retry_dupa_sec is not None:
        return ant.retry_dupa_sec
    candidati = [
        (t - acum).total_seconds() for t in (ant.reset_cereri_la, ant.reset_tokeni_la) if t is not None
    ]
    if candidati:
        return max(0.0, min(candidati))
    return _retry_delay_gemini(corp)


def _retry_delay_gemini(corp: Any) -> float | None:
    """Gemini pune pauza în `error.details[].retryDelay` (`"34s"`)."""
    if not isinstance(corp, dict) or not isinstance(corp.get("error"), dict):
        return None
    for d in corp["error"].get("details", []) or []:
        if isinstance(d, dict) and "retryDelay" in d:
            return antete_limita.durata_sec(str(d["retryDelay"]))
    return None


def corp_json(date: dict[str, Any]) -> bytes:
    return json.dumps(date, ensure_ascii=False).encode()
