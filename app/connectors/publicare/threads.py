"""Conectorul Threads (F16.2): Threads API (Meta), postări text cu publicare în doi pași.

- Autorizarea: `threads.net/oauth/authorize`, codul -> token scurt (`POST
graph.threads.net/oauth/access_token`)
  -> token lung (`GET /access_token?grant_type=th_exchange_token`, 60 de zile); reîmprospătarea:
  `GET /refresh_access_token?grant_type=th_refresh_token`. Contul extern = id-ul utilizatorului (`GET
  /v1.0/me`).
- `trimite`: containerul (`POST /v1.0/{id}/threads`, `media_type=TEXT`) apoi publicarea
  (`POST /v1.0/{id}/threads_publish`). Un container rămas nepublicat nu e o postare (nu se dublează nimic).
- `verifica`: postările utilizatorului (`GET /v1.0/{id}/threads`), după text. `stare`: `GET /v1.0/{media}`.
- `limite`: `GET /v1.0/{id}/threads_publishing_limit` (`quota_usage` din `config.quota_total`, 250 / 24 h).

Tokenul pleacă doar în antetul `Authorization` (și la schimbul în token lung / reîmprospătare).
# NEVERIFICAT: aplicația Threads aprobată (`threads_basic`, `threads_content_publish`), acceptarea antetului
`Authorization` la schimbul în token lung; API simulat (contract HTTP local), D-026.
"""

import uuid
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import get_settings
from app.connectors.contract import EfectDeTrimis, Limite, RezultatPlatforma, StarePostare, Token
from app.connectors.publicare.baza import (
    ClientHttp,
    DepozitBaza,
    DepozitTokenuri,
    cu_expirare,
    text_postare,
    token_sau_autentificare,
)
from app.operare.motor import EroareDefinitiva

API = "https://graph.threads.net"
SCOPURI = ("threads_basic", "threads_content_publish")
TEXT_MAXIM = 500


class ConectorThreads:
    canal = "threads"

    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        depozit: DepozitTokenuri | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.app_id, self._secret = app_id, app_secret
        self.depozit = depozit or DepozitBaza()
        self.http = ClientHttp(API, transport)

    @classmethod
    def din_setari(cls) -> "ConectorThreads":
        s = get_settings()
        return cls(app_id=s.threads_app_id, app_secret=s.threads_app_secret.get_secret_value())

    def _token(self, tenant_id: uuid.UUID) -> Token:
        return token_sau_autentificare(self.depozit, tenant_id, self.canal)

    # --- autorizare -----------------------------------------------------------------------------------------
    def url_autorizare(self, stare: str, redirect: str) -> str:
        q = {
            "client_id": self.app_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": ",".join(SCOPURI),
            "state": stare,
        }
        return f"https://threads.net/oauth/authorize?{urlencode(q)}"

    def schimba_cod(self, cod: str, redirect: str) -> Token:
        scurt = self.http.cere(
            "POST",
            "oauth/access_token",
            data={
                "client_id": self.app_id,
                "client_secret": self._secret,
                "grant_type": "authorization_code",
                "redirect_uri": redirect,
                "code": cod,
            },
        ).json()
        ts = Token(str(scurt["access_token"]), None, "", str(scurt.get("user_id", "")), SCOPURI)
        lung = self.http.cere(
            "GET",
            "access_token",
            token=ts,
            params={"grant_type": "th_exchange_token", "client_secret": self._secret},
        ).json()
        tl = Token(str(lung["access_token"]), None, "", "", SCOPURI)
        uid = str(self.http.cere("GET", "v1.0/me", token=tl, params={"fields": "id"}).json()["id"])
        return cu_expirare(Token(tl.acces, None, "", uid, SCOPURI), lung.get("expires_in"))

    def reimprospateaza(self, token: Token) -> Token:
        d = self.http.cere(
            "GET", "refresh_access_token", token=token, params={"grant_type": "th_refresh_token"}
        ).json()
        return cu_expirare(
            Token(str(d["access_token"]), None, "", token.cont_extern, token.scopuri), d.get("expires_in")
        )

    # --- publicare ------------------------------------------------------------------------------------------
    @staticmethod
    def text(payload: dict[str, Any]) -> str:
        return text_postare(payload)[:TEXT_MAXIM]

    def trimite(self, efect: EfectDeTrimis) -> RezultatPlatforma:
        t = self._token(efect.tenant_id)
        cont = self.http.cere(
            "POST",
            f"v1.0/{t.cont_extern}/threads",
            token=t,
            data={"media_type": "TEXT", "text": self.text(efect.payload)},
        ).json()
        r = self.http.cere(
            "POST", f"v1.0/{t.cont_extern}/threads_publish", token=t, data={"creation_id": str(cont["id"])}
        )
        mid = str(r.json().get("id", ""))
        if not mid:
            raise EroareDefinitiva("Threads nu a întors identificatorul postării")
        return RezultatPlatforma(mid, self._permalink(t, mid))

    def _permalink(self, t: Token, mid: str) -> str:
        p = self.http.cere("GET", f"v1.0/{mid}", token=t, params={"fields": "id,permalink"}).json()
        return str(p.get("permalink") or f"https://www.threads.net/t/{mid}")

    def verifica(self, efect: EfectDeTrimis) -> RezultatPlatforma | None:
        t = self._token(efect.tenant_id)
        text = self.text(efect.payload)
        r = self.http.cere(
            "GET",
            f"v1.0/{t.cont_extern}/threads",
            token=t,
            params={"fields": "id,text,permalink", "limit": "50"},
        ).json()
        for p in r.get("data", []):
            if p.get("text") == text:
                return RezultatPlatforma(
                    str(p["id"]), str(p.get("permalink") or f"https://www.threads.net/t/{p['id']}")
                )
        return None

    def stare(self, tenant_id: uuid.UUID, id_extern: str) -> StarePostare:
        r = self.http.cere(
            "GET",
            f"v1.0/{id_extern}",
            token=self._token(tenant_id),
            params={"fields": "id"},
            clasifica_erori=False,
        )
        if r.status_code in (400, 404) and "does not exist" in r.text:
            return StarePostare.INEXISTENTA
        self.http.clasificator(r)
        return StarePostare.PUBLICATA

    def limite(self, tenant_id: uuid.UUID) -> Limite:
        t = self._token(tenant_id)
        r = self.http.cere(
            "GET",
            f"v1.0/{t.cont_extern}/threads_publishing_limit",
            token=t,
            params={"fields": "quota_usage,config"},
        ).json()
        d = (r.get("data") or [{}])[0]
        total = int((d.get("config") or {}).get("quota_total", 0)) or None
        folosit = int(d.get("quota_usage", 0))
        return Limite(
            "endpointul threads_publishing_limit",
            None if total is None else total - folosit,
            total,
            None if not total else round(100.0 * folosit / total, 1),
        )
