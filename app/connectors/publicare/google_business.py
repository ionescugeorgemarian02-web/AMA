"""Conectorul Google Business Profile (F16.2): postări locale („Noutăți”) pe fișa firmei.

- Autorizarea: OAuth Google (scopul `business.manage`), același client ca YouTube; contul extern = prima
locație a
  primului cont (`accounts` -> `accounts/{a}/locations`), forma `accounts/{a}/locations/{l}`.
- `trimite`: `POST v4/{locatie}/localPosts` (`topicType=STANDARD`, `summary` = textul aprobat, buton opțional
  „Află mai multe” spre `link`). `verifica`: lista postărilor locației, după `summary`. `stare`: `state`
  (`LIVE` publicată, `PROCESSING` în procesare, `REJECTED` respinsă).
- `limite`: Google nu expune cota prin API; se numără postările de azi și se scad din plafonul zilnic intern
  `PLAFON_ZI` [I] (fișa nu e un canal de volum), cu sursa spusă.

# NEVERIFICAT: accesul la API (formularul Google Business Profile API, proiect aprobat), cota pe minut,
# versiunea
v4 a `localPosts` pe contul real; API simulat (contract HTTP local), D-026.
"""

import datetime as dt
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

API = "https://mybusiness.googleapis.com"
CONTURI = "https://mybusinessaccountmanagement.googleapis.com/v1"
INFO = "https://mybusinessbusinessinformation.googleapis.com/v1"
SCOPURI = ("https://www.googleapis.com/auth/business.manage",)
PLAFON_ZI = 10  # [I] postări pe zi și locație, plafon intern
TEXT_MAXIM = 1500
STARI = {"LIVE": StarePostare.PUBLICATA, "PROCESSING": StarePostare.IN_PROCESARE}


class ConectorGoogleBusiness:
    canal = "google_business"

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
    def din_setari(cls) -> "ConectorGoogleBusiness":
        s = get_settings()
        return cls(client_id=s.google_client_id, client_secret=s.google_client_secret.get_secret_value())

    def _token(self, tenant_id: uuid.UUID) -> Token:
        return token_sau_autentificare(self.depozit, tenant_id, self.canal)

    # --- autorizare -----------------------------------------------------------------------------------------
    def url_autorizare(self, stare: str, redirect: str) -> str:
        q = {
            "client_id": self.client_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": " ".join(SCOPURI),
            "access_type": "offline",
            "prompt": "consent",
            "state": stare,
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(q)}"

    def _schimb(self, **date: str) -> dict[str, Any]:
        r = self.http.cere(
            "POST",
            "https://oauth2.googleapis.com/token",
            data={"client_id": self.client_id, "client_secret": self._secret, **date},
        )
        return dict(r.json())

    def _locatie(self, t: Token) -> str:
        conturi = self.http.cere("GET", f"{CONTURI}/accounts", token=t).json().get("accounts", [])
        if not conturi:
            raise EroareDefinitiva("contul Google nu administrează nicio fișă de firmă")
        cont = str(conturi[0]["name"])
        loc = self.http.cere("GET", f"{INFO}/{cont}/locations", token=t, params={"readMask": "name,title"})
        locatii = loc.json().get("locations", [])
        if not locatii:
            raise EroareDefinitiva("contul Google nu are nicio locație")
        return f"{cont}/{locatii[0]['name']}"

    def schimba_cod(self, cod: str, redirect: str) -> Token:
        d = self._schimb(code=cod, redirect_uri=redirect, grant_type="authorization_code")
        t = Token(str(d["access_token"]), None, str(d.get("refresh_token", "")), "", SCOPURI)
        return cu_expirare(
            Token(t.acces, None, t.reimprospatare, self._locatie(t), SCOPURI), d.get("expires_in")
        )

    def reimprospateaza(self, token: Token) -> Token:
        if not token.reimprospatare:
            raise EroareAutentificare("Google nu a dat token de reîmprospătare: reautorizare")
        d = self._schimb(grant_type="refresh_token", refresh_token=token.reimprospatare)
        nou = Token(str(d["access_token"]), None, token.reimprospatare, token.cont_extern, token.scopuri)
        return cu_expirare(nou, d.get("expires_in"))

    # --- publicare ------------------------------------------------------------------------------------------
    @staticmethod
    def text(payload: dict[str, Any]) -> str:
        return text_postare(payload)[:TEXT_MAXIM]

    def trimite(self, efect: EfectDeTrimis) -> RezultatPlatforma:
        t = self._token(efect.tenant_id)
        corp: dict[str, Any] = {
            "languageCode": "ro",
            "summary": self.text(efect.payload),
            "topicType": "STANDARD",
        }
        if efect.payload.get("link"):
            corp["callToAction"] = {"actionType": "LEARN_MORE", "url": efect.payload["link"]}
        r = self.http.cere("POST", f"v4/{t.cont_extern}/localPosts", token=t, json=corp).json()
        if not r.get("name"):
            raise EroareDefinitiva("Google nu a întors numele postării")
        return RezultatPlatforma(str(r["name"]), str(r.get("searchUrl") or "https://business.google.com/"))

    def _postari(self, t: Token) -> list[dict[str, Any]]:
        r = self.http.cere("GET", f"v4/{t.cont_extern}/localPosts", token=t, params={"pageSize": "100"})
        return list(r.json().get("localPosts", []))

    def verifica(self, efect: EfectDeTrimis) -> RezultatPlatforma | None:
        t = self._token(efect.tenant_id)
        text = self.text(efect.payload)
        for p in self._postari(t):
            if p.get("summary") == text:
                return RezultatPlatforma(
                    str(p["name"]), str(p.get("searchUrl") or "https://business.google.com/")
                )
        return None

    def stare(self, tenant_id: uuid.UUID, id_extern: str) -> StarePostare:
        r = self.http.cere("GET", f"v4/{id_extern}", token=self._token(tenant_id), clasifica_erori=False)
        if r.status_code == 404:
            return StarePostare.INEXISTENTA
        self.http.clasificator(r)
        s = str(r.json().get("state", ""))
        if s == "REJECTED":
            raise EroareDefinitiva("Google a respins postarea (politica de conținut)")
        return STARI.get(s, StarePostare.IN_PROCESARE)

    def limite(self, tenant_id: uuid.UUID) -> Limite:
        t = self._token(tenant_id)
        azi = dt.datetime.now(dt.UTC).date().isoformat()
        n = sum(1 for p in self._postari(t) if str(p.get("createTime", "")).startswith(azi))
        return Limite(
            "postările de azi citite din API, față de plafonul intern pe zi", PLAFON_ZI - n, PLAFON_ZI
        )
