"""Conectorul LinkedIn (F9.5): Posts API (`/rest/posts`, antetele `LinkedIn-Version` și Rest.li 2.0).

- Profilul (canalul `linkedin`): aplicație self-serve, permisiunea `w_member_social`; autorul e
  `urn:li:person:{sub}` din `userinfo` (OpenID). Automat de la început (15.1).
- Pagina de companie (canalul `linkedin_pagina`): Community Management API, cu review; autorul e
  `urn:li:organization:{id}`, din `organizationAcls` (administrator). Asistat până la aprobare.
- `verifica`: postările autorului (`q=author`), după text. Limita: LinkedIn nu o expune prin API; se citesc
  postările de azi ale autorului și se scad din plafonul zilnic documentat (`PLAFON_ZI` [I]).
- Tokenul: 60 de zile; reîmprospătarea există doar pentru aplicațiile aprobate (altfel: reautorizare).

# NEVERIFICAT: versiunea API (`AMA_LINKEDIN_VERSIUNE`), plafonul zilnic, review-ul Community Management;
API simulat (contract HTTP local).
"""

import datetime as dt
import uuid
from typing import Any
from urllib.parse import quote, urlencode

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

API = "https://api.linkedin.com"
OAUTH = "https://www.linkedin.com/oauth/v2"
SCOPURI_PROFIL = ("openid", "profile", "w_member_social")
SCOPURI_PAGINA = ("openid", "profile", "w_organization_social", "r_organization_social")
PLAFON_ZI = 150  # [I] postări pe zi și membru, din documentația de limite


def link_postare(urn: str) -> str:
    return f"https://www.linkedin.com/feed/update/{urn}/"


class ConectorLinkedin:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        pagina: bool = False,
        versiune: str = "202510",
        depozit: DepozitTokenuri | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.client_id, self._secret, self.pagina, self.versiune = client_id, client_secret, pagina, versiune
        self.canal = "linkedin_pagina" if pagina else "linkedin"
        self.scopuri = SCOPURI_PAGINA if pagina else SCOPURI_PROFIL
        self.depozit = depozit or DepozitBaza()
        self.http = ClientHttp(API, transport)

    @classmethod
    def din_setari(cls, pagina: bool = False) -> "ConectorLinkedin":
        s = get_settings()
        return cls(
            client_id=s.linkedin_client_id,
            client_secret=s.linkedin_client_secret.get_secret_value(),
            pagina=pagina,
            versiune=s.linkedin_versiune,
        )

    @classmethod
    def pagina_din_setari(cls) -> "ConectorLinkedin":
        return cls.din_setari(pagina=True)

    def _antete(self) -> dict[str, str]:
        return {"LinkedIn-Version": self.versiune, "X-Restli-Protocol-Version": "2.0.0"}

    def _token(self, tenant_id: uuid.UUID) -> Token:
        return token_sau_autentificare(self.depozit, tenant_id, self.canal)

    # --- autorizare -----------------------------------------------------------------------------------------
    def url_autorizare(self, stare: str, redirect: str) -> str:
        q = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect,
            "state": stare,
            "scope": " ".join(self.scopuri),
        }
        return f"{OAUTH}/authorization?{urlencode(q)}"

    def _schimb(self, **date: str) -> dict[str, Any]:
        r = self.http.cere(
            "POST",
            f"{OAUTH}/accessToken",
            data={"client_id": self.client_id, "client_secret": self._secret, **date},
        )
        return dict(r.json())

    def _autor(self, t: Token) -> str:
        if not self.pagina:
            sub = self.http.cere("GET", "v2/userinfo", token=t).json().get("sub")
            return f"urn:li:person:{sub}"
        r = self.http.cere(
            "GET",
            "rest/organizationAcls",
            token=t,
            headers=self._antete(),
            params={"q": "roleAssignee", "role": "ADMINISTRATOR", "state": "APPROVED"},
        ).json()
        org = [e["organization"] for e in r.get("elements", []) if e.get("organization")]
        if not org:
            raise EroareDefinitiva("contul nu administrează nicio pagină de companie")
        return str(org[0])

    def schimba_cod(self, cod: str, redirect: str) -> Token:
        d = self._schimb(grant_type="authorization_code", code=cod, redirect_uri=redirect)
        t = Token(str(d["access_token"]), None, str(d.get("refresh_token", "")), "", self.scopuri)
        return cu_expirare(
            Token(t.acces, None, t.reimprospatare, self._autor(t), t.scopuri), d.get("expires_in")
        )

    def reimprospateaza(self, token: Token) -> Token:
        if not token.reimprospatare:
            raise EroareAutentificare("LinkedIn nu a dat token de reîmprospătare: reautorizare")
        d = self._schimb(grant_type="refresh_token", refresh_token=token.reimprospatare)
        nou = Token(
            str(d["access_token"]),
            None,
            str(d.get("refresh_token", token.reimprospatare)),
            token.cont_extern,
            token.scopuri,
        )
        return cu_expirare(nou, d.get("expires_in"))

    # --- publicare ------------------------------------------------------------------------------------------
    def trimite(self, efect: EfectDeTrimis) -> RezultatPlatforma:
        t = self._token(efect.tenant_id)
        corp = {
            "author": t.cont_extern,
            "commentary": text_postare(efect.payload),
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        r = self.http.cere("POST", "rest/posts", token=t, json=corp, headers=self._antete())
        urn = r.headers.get("x-restli-id") or str((r.json() if r.content else {}).get("id", ""))
        if not urn:
            raise EroareDefinitiva("LinkedIn nu a întors identificatorul postării")
        return RezultatPlatforma(urn, link_postare(urn))

    def _ale_autorului(self, t: Token) -> list[dict[str, Any]]:
        r = self.http.cere(
            "GET",
            "rest/posts",
            token=t,
            headers=self._antete(),
            params={"author": t.cont_extern, "q": "author", "count": "50"},
        ).json()
        return list(r.get("elements", []))

    def verifica(self, efect: EfectDeTrimis) -> RezultatPlatforma | None:
        t = self._token(efect.tenant_id)
        text = text_postare(efect.payload)
        for p in self._ale_autorului(t):
            if p.get("commentary") == text:
                return RezultatPlatforma(str(p["id"]), link_postare(str(p["id"])))
        return None

    def stare(self, tenant_id: uuid.UUID, id_extern: str) -> StarePostare:
        t = self._token(tenant_id)
        r = self.http.cere(
            "GET",
            f"rest/posts/{quote(id_extern, safe='')}",
            token=t,
            headers=self._antete(),
            clasifica_erori=False,
        )
        if r.status_code == 404:
            return StarePostare.INEXISTENTA
        self.http.clasificator(r)
        return (
            StarePostare.PUBLICATA
            if r.json().get("lifecycleState") == "PUBLISHED"
            else StarePostare.IN_PROCESARE
        )

    def limite(self, tenant_id: uuid.UUID) -> Limite:
        t = self._token(tenant_id)
        azi = dt.datetime.now(dt.UTC).date()
        n = sum(
            1
            for p in self._ale_autorului(t)
            if dt.datetime.fromtimestamp(int(p.get("createdAt", 0)) / 1000, dt.UTC).date() == azi
        )
        return Limite(
            "postările de azi citite din API, față de plafonul zilnic documentat", PLAFON_ZI - n, PLAFON_ZI
        )
