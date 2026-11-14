"""Interfața comună a conectorilor de publicare (F9.1, docs/15, 7.3, 7.5).

Un conector de publicare face cinci lucruri și nu decide nimic: autorizarea (OAuth: adresa de consimțământ,
schimbul
codului, reîmprospătarea), publicarea (`trimite`), căutarea unei publicări deja făcute (`verifica`, înainte de
orice
reîncercare), starea unei postări (`stare`) și limitele citite de la platformă (`limite`, 15.7: „nu
ghicește”).
Erorile se clasifică după 7.5 (`clasifica`): autentificare → pauză și reautorizare, temporară → reîncercare
după
`verifica`, definitivă → coada de erori. Conectorii se cheamă DOAR din executorul de efecte (garda
`check_efecte`).

Tokenurile nu intră niciodată în efect, în rezultat, în jurnale sau în adresa cererii: se rezolvă la execuție
dintr-un
`DepozitTokenuri` (în producție: `publicare.canale`, tabelul criptat `publicare_conturi`) și pleacă
doar în antetul
`Authorization`.
"""

import datetime as dt
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, runtime_checkable

import httpx

from app.connectors.contract import (
    EfectDeTrimis,
    Limite,
    RezultatPlatforma,
    StarePostare,
    Token,
)
from app.operare.motor import EroareAutentificare, EroareDefinitiva, EroareTemporara


class DepozitTokenuri(Protocol):
    def citeste(self, tenant_id: uuid.UUID, canal: str) -> Token | None: ...


@dataclass
class DepozitInMemorie:
    """Depozit simplu (teste, conturile agenției în modul de test)."""

    tokenuri: dict[tuple[uuid.UUID, str], Token] = field(default_factory=dict)

    def citeste(self, tenant_id: uuid.UUID, canal: str) -> Token | None:
        return self.tokenuri.get((tenant_id, canal))

    def pune(self, tenant_id: uuid.UUID, canal: str, token: Token) -> None:
        self.tokenuri[(tenant_id, canal)] = token


class DepozitBaza:
    """Depozitul de producție: tokenul criptat din `publicare_conturi` (citit la execuție, pe clientul
    efectului)."""

    def citeste(self, tenant_id: uuid.UUID, canal: str) -> Token | None:
        from app.publicare import canale  # la execuție: conectorul nu depinde de publicare la import

        return canale.token_pentru(tenant_id, canal)


@runtime_checkable
class ConectorPublicare(Protocol):
    """Contractul comun (F9.1). Toate metodele care ating platforma aruncă erorile clasificate din
    `app.operare.motor`."""

    canal: str

    def url_autorizare(self, stare: str, redirect: str) -> str: ...

    def schimba_cod(self, cod: str, redirect: str) -> Token: ...

    def reimprospateaza(self, token: Token) -> Token: ...

    def trimite(self, efect: EfectDeTrimis) -> RezultatPlatforma: ...

    def verifica(self, efect: EfectDeTrimis) -> RezultatPlatforma | None: ...

    def stare(self, tenant_id: uuid.UUID, id_extern: str) -> StarePostare: ...

    def limite(self, tenant_id: uuid.UUID) -> Limite: ...


# --- clasificarea erorilor (7.5)
# -----------------------------------------------------------------------------------


def mesaj_platforma(r: httpx.Response) -> str:
    """Mesajul de eroare al platformei, scurt, fără să ecou-iască cererea (tokenul nu e niciodată în corp)."""
    try:
        corp = r.json()
    except ValueError:
        return r.text[:200]
    if isinstance(corp, dict):
        e = corp.get("error", corp.get("message", corp))
        if isinstance(e, dict):
            e = e.get("message", e.get("code", json.dumps(e)[:200]))
        return str(e)[:200]
    return str(corp)[:200]


def clasifica(r: httpx.Response) -> None:
    """Clasificarea implicită după cod (7.5). Conectorii o rafinează (de ex. Meta: codul 190 = token)."""
    if r.status_code < 400:
        return
    m = f"{r.status_code}: {mesaj_platforma(r)}"
    if r.status_code == 401:
        raise EroareAutentificare(m)
    if r.status_code in (408, 409, 425, 429) or r.status_code >= 500:
        raise EroareTemporara(m)
    raise EroareDefinitiva(m)


@dataclass
class ClientHttp:
    """Clientul HTTP comun: adresa de bază, transportul (în teste: platforma simulată), timpi, clasificarea.
    `antete` păstrează antetele ultimului răspuns (limitele se citesc din ele, 15.7)."""

    baza: str
    transport: httpx.BaseTransport | None = None
    timeout: float = 30.0
    clasificator: Callable[[httpx.Response], None] = clasifica
    antete: dict[str, str] = field(default_factory=dict)
    # Înregistrarea fluxului (App Review, audit): pașii HTTP, fără parametri, corpuri sau tokenuri.
    inregistrare: list[dict[str, Any]] | None = None

    def cere(
        self, metoda: str, cale: str, *, token: Token | None = None, clasifica_erori: bool = True, **kw: Any
    ) -> httpx.Response:
        antete = dict(kw.pop("headers", {}) or {})
        if token is not None:
            antete["Authorization"] = f"Bearer {token.acces}"
        url = cale if cale.startswith("http") else self.baza.rstrip("/") + "/" + cale.lstrip("/")
        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout) as c:
                r = c.request(metoda, url, headers=antete, **kw)
        except httpx.TimeoutException as exc:
            raise EroareTemporara(f"timeout: {type(exc).__name__}") from None
        except httpx.TransportError as exc:
            raise EroareTemporara(f"rețea: {type(exc).__name__}") from None
        self.antete = {k.lower(): v for k, v in r.headers.items()}
        if self.inregistrare is not None:
            self.inregistrare.append(
                {
                    "metoda": metoda,
                    "cale": httpx.URL(url).path,
                    "status": r.status_code,
                    "la": dt.datetime.now(dt.UTC).isoformat(),
                }
            )
        if clasifica_erori:
            self.clasificator(r)
        return r


def token_sau_autentificare(depozit: DepozitTokenuri, tenant_id: uuid.UUID, canal: str) -> Token:
    """Tokenul contului, sau `EroareAutentificare` (lipsă sau expirat: canalul cere reautorizare)."""
    t = depozit.citeste(tenant_id, canal)
    if t is None:
        raise EroareAutentificare(f"canalul „{canal}” nu este autorizat")
    if t.expirat():
        raise EroareAutentificare(f"tokenul canalului „{canal}” a expirat")
    return t


def text_postare(payload: dict[str, Any]) -> str:
    """Textul final: textul aprobat + hashtag-urile (o singură regulă pentru toate canalele)."""
    text = str(payload.get("text", "")).strip()
    tags = [str(h).lstrip("#") for h in payload.get("taguri", []) if str(h).strip("# ")]
    return text + ("\n\n" + " ".join(f"#{h}" for h in tags) if tags else "")


def cu_expirare(token: Token, secunde: int | None, acum: dt.datetime | None = None) -> Token:
    acum = acum or dt.datetime.now(dt.UTC)
    return replace(token, expira_la=acum + dt.timedelta(seconds=int(secunde)) if secunde else None)
