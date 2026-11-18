"""Conectorul Pinterest (F16.2): API v5, pinuri pe un panou al contului de firmă.

- Autorizarea: OAuth 2.0 (`pinterest.com/oauth`), schimbul codului la `POST /v5/oauth/token` cu
autentificare Basic
  (id + secret ai aplicației); contul extern = primul panou (`GET /v5/boards`), unde se pun pinurile.
- `trimite`: `POST /v5/pins` cu titlu, descriere (textul aprobat + hashtag-uri), link și imaginea
(`imagine_url`,
  obligatorie: Pinterest nu primește pinuri fără imagine).
- `verifica`: pinurile panoului (`GET /v5/boards/{id}/pins`), după descriere. `stare`: `GET /v5/pins/{id}`.
- `limite`: antetele `x-ratelimit-remaining` / `x-ratelimit-limit` ale ultimului răspuns (15.7: nu ghicește).

# NEVERIFICAT: accesul „Standard” (aplicație aprobată de Pinterest), scopurile, forma antetelor de limită
# pe contul
real; API simulat (contract HTTP local), D-026.
"""

import base64
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
from app.operare.motor import EroareAutentificare, EroareDefinitiva

API = "https://api.pinterest.com/v5"
SCOPURI = ("boards:read", "pins:read", "pins:write")
TITLU_MAXIM, DESCRIERE_MAXIMA = 100, 500


def link_pin(pid: str) -> str:
    return f"https://www.pinterest.com/pin/{pid}/"


class ConectorPinterest:
    canal = "pinterest"

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        depozit: DepozitTokenuri | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.client_id, self._secret = client_id, client_secret
        self.depozit = depozit or DepozitBaza()
        self.http = ClientHttp(API, transport)

    @classmethod
    def din_setari(cls) -> "ConectorPinterest":
        s = get_settings()
        return cls(
            client_id=s.pinterest_client_id, client_secret=s.pinterest_client_secret.get_secret_value()
        )

    def _token(self, tenant_id: uuid.UUID) -> Token:
        return token_sau_autentificare(self.depozit, tenant_id, self.canal)

    # --- autorizare -----------------------------------------------------------------------------------------
    def url_autorizare(self, stare: str, redirect: str) -> str:
        q = {
            "client_id": self.client_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": ",".join(SCOPURI),
            "state": stare,
        }
        return f"https://www.pinterest.com/oauth/?{urlencode(q)}"

    def _schimb(self, **date: str) -> dict[str, Any]:
        cheie = base64.b64encode(f"{self.client_id}:{self._secret}".encode()).decode()
        r = self.http.cere("POST", "oauth/token", data=date, headers={"Authorization": f"Basic {cheie}"})
        return dict(r.json())

    def schimba_cod(self, cod: str, redirect: str) -> Token:
        d = self._schimb(grant_type="authorization_code", code=cod, redirect_uri=redirect)
        t = Token(str(d["access_token"]), None, str(d.get("refresh_token", "")), "", SCOPURI)
        panouri = self.http.cere("GET", "boards", token=t, params={"page_size": "25"}).json().get("items", [])
        if not panouri:
            raise EroareDefinitiva("contul Pinterest nu are niciun panou")
        return cu_expirare(
            Token(t.acces, None, t.reimprospatare, str(panouri[0]["id"]), SCOPURI), d.get("expires_in")
        )

    def reimprospateaza(self, token: Token) -> Token:
        if not token.reimprospatare:
            raise EroareAutentificare("Pinterest nu a dat token de reîmprospătare: reautorizare")
        d = self._schimb(grant_type="refresh_token", refresh_token=token.reimprospatare)
        nou = Token(str(d["access_token"]), None, token.reimprospatare, token.cont_extern, token.scopuri)
        return cu_expirare(nou, d.get("expires_in"))

    # --- publicare ------------------------------------------------------------------------------------------
    @staticmethod
    def descriere(payload: dict[str, Any]) -> str:
        return text_postare(payload)[:DESCRIERE_MAXIMA]

    def trimite(self, efect: EfectDeTrimis) -> RezultatPlatforma:
        t = self._token(efect.tenant_id)
        p = efect.payload
        if not p.get("imagine_url"):
            raise EroareDefinitiva("Pinterest cere o imagine (imagine_url) pentru pin")
        corp = {
            "board_id": t.cont_extern,
            "title": str(p.get("titlu") or p.get("text", ""))[:TITLU_MAXIM],
            "description": self.descriere(p),
            "link": p.get("link") or None,
            "alt_text": str(p.get("alt", ""))[:500] or None,
            "media_source": {"source_type": "image_url", "url": p["imagine_url"]},
        }
        pid = str(self.http.cere("POST", "pins", token=t, json=corp).json().get("id", ""))
        if not pid:
            raise EroareDefinitiva("Pinterest nu a întors identificatorul pinului")
        return RezultatPlatforma(pid, link_pin(pid))

    def verifica(self, efect: EfectDeTrimis) -> RezultatPlatforma | None:
        t = self._token(efect.tenant_id)
        text = self.descriere(efect.payload)
        r = self.http.cere("GET", f"boards/{t.cont_extern}/pins", token=t, params={"page_size": "100"}).json()
        for pin in r.get("items", []):
            if pin.get("description") == text:
                return RezultatPlatforma(str(pin["id"]), link_pin(str(pin["id"])))
        return None

    def stare(self, tenant_id: uuid.UUID, id_extern: str) -> StarePostare:
        r = self.http.cere("GET", f"pins/{id_extern}", token=self._token(tenant_id), clasifica_erori=False)
        if r.status_code == 404:
            return StarePostare.INEXISTENTA
        self.http.clasificator(r)
        return StarePostare.PUBLICATA

    def limite(self, tenant_id: uuid.UUID) -> Limite:
        t = self._token(tenant_id)
        self.http.cere("GET", "user_account", token=t)
        a = self.http.antete
        ramase, total = a.get("x-ratelimit-remaining"), a.get("x-ratelimit-limit")
        if ramase is None:
            return Limite("antetele x-ratelimit lipsesc din răspuns", None, None, None)
        return Limite("antetele x-ratelimit-* ale API-ului v5", int(ramase), int(total) if total else None)
