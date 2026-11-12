"""Clientul unificat (F3.2): un singur mod de a apela orice furnizor, prin adaptorul tipului lui de API.

Doar `httpx`, cu transport injectabil (testele nu ating rețeaua). Reguli:
- cheia vine ca argument și ajunge doar în antetul cererii; nu se păstrează, nu se loghează;
- erorile nu poartă adresa, antetele, corpul cererii sau mesajul furnizorului (care poate repeta promptul):
doar fel,
  status și un cod scurt;
- logger-ul `httpx` este coborât la WARNING (altfel ar scrie adresa fiecărei cereri).
"""

import logging
import time
from collections.abc import Callable
from dataclasses import replace

import httpx

from app.gateway import ceas
from app.gateway.adaptoare import adaptor_pentru
from app.gateway.adaptoare.baza import clasifica, json_sau_gol
from app.gateway.erori import EroareFurnizor, IesireInvalida
from app.gateway.iesire import Iesire, schema_json
from app.gateway.structurat import IesireNevalida, IesireStructurata, ruleaza_structurat
from app.gateway.tipuri import CerereModel, Destinatie, Mesaj, RaspunsModel

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

TIMEOUT_IMPLICIT_SEC = 60.0
_transport: httpx.BaseTransport | None = None


def seteaza_transport(transport: httpx.BaseTransport | None) -> None:
    """Transportul tuturor apelurilor (teste: `httpx.MockTransport`). `None` = rețeaua reală."""
    global _transport
    _transport = transport


def trimite(
    dest: Destinatie,
    cheie: str | None,
    cerere: CerereModel,
    *,
    timeout_sec: float = TIMEOUT_IMPLICIT_SEC,
) -> RaspunsModel:
    """O singură cerere HTTP. Ridică `EroareFurnizor` (limita | server | retea | autentificare | cerere |
    continut)."""
    adaptor = adaptor_pentru(dest.tip_api)
    cerere_http = adaptor.cerere(dest, cheie, cerere)
    start = time.monotonic()
    try:
        with httpx.Client(transport=_transport, timeout=timeout_sec) as http:
            r = http.send(cerere_http)
    except httpx.TimeoutException:
        raise EroareFurnizor("retea", detaliu="timeout") from None
    except httpx.HTTPError as exc:
        raise EroareFurnizor("retea", detaliu=type(exc).__name__) from None
    acum = ceas.acum()
    if r.status_code >= 400:
        raise clasifica(r, json_sau_gol(r), acum)
    raspuns = adaptor.raspuns(r, acum)
    return replace(raspuns, durata_ms=int((time.monotonic() - start) * 1000))


def apeleaza_structurat(
    dest: Destinatie,
    cheie: str | None,
    mesaje: tuple[Mesaj, ...],
    schema: type[Iesire],
    *,
    max_tokeni: int = 1024,
    temperatura: float = 0.2,
    trimite_fn: Callable[[Destinatie, str | None, CerereModel], RaspunsModel] | None = None,
) -> IesireStructurata:
    """Apel structurat pe UN model: cerere cu schemă (unde furnizorul o suportă) sau instrucțiune, validare, o
    singură reparație (8.6), apoi `IesireInvalida`. Reîncercările, cotele și lanțul de rezervă sunt ale
    gateway-ului
    (`apel`), nu ale clientului."""
    trimitere = trimite_fn or trimite
    sj = schema_json(schema)
    nativ = dest.schema_nativa

    def un_apel(m: tuple[Mesaj, ...]) -> RaspunsModel:
        c = CerereModel(
            mesaje=m,
            max_tokeni=max_tokeni,
            temperatura=temperatura,
            schema_json=sj if nativ else None,
            schema_nume=schema.__name__,
        )
        return trimitere(dest, cheie, c)

    try:
        return ruleaza_structurat(un_apel, mesaje, schema, nativ=nativ)
    except IesireNevalida as exc:
        raise IesireInvalida(f"ieșire în afara schemei după o reparație: {exc.eroare}") from None
