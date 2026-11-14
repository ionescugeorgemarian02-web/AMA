"""Conectorul Facebook Pages (F9.2): Graph API, publicare pe pagină.

- Autorizarea: dialogul OAuth al Meta → cod → token de utilizator scurt → token lung (`fb_exchange_token`) →
  tokenul paginii (`me/accounts`). Tokenul paginii primește expirarea tokenului lung (60 de zile [I]), ca
  gardianul (F9.8) să ceară reautorizarea la timp. Meta nu are token de reîmprospătare: se reface schimbul.
- Publicarea: `POST /{pagina}/feed` (`message`, opțional `link`), apoi `permalink_url`.
- `verifica`: Graph nu are cheie de idempotență; se caută în postările recente ale paginii textul exact.
- Erorile Graph: codul 190 (și subcodurile lui) = token; `is_transient`, codurile 1, 2, 4, 17, 32, 341, 613 =
  temporară (limită de rată); restul 4xx = definitivă (7.5).
- Limitele: antetele `X-App-Usage` / `X-Page-Usage` / `X-Business-Use-Case-Usage` (procentul folosit).

# NEVERIFICAT: versiunea Graph (`AMA_META_GRAPH_VERSIUNE`), permisiunile cerute în App Review, comportamentul
real în modul de dezvoltare; testat pe Graph simulat (contract HTTP local).
"""

import json
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
    clasifica,
    cu_expirare,
    mesaj_platforma,
    text_postare,
    token_sau_autentificare,
)
from app.operare.motor import EroareAutentificare, EroareDefinitiva, EroareTemporara

GRAPH = "https://graph.facebook.com"
SCOPURI_PAGINI = ("pages_show_list", "pages_read_engagement", "pages_manage_posts")
CODURI_TEMPORARE = {1, 2, 4, 17, 32, 341, 613, 80001}
ANTETE_UTILIZARE = ("x-page-usage", "x-app-usage", "x-business-use-case-usage")


def clasifica_graph(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    try:
        e = r.json().get("error", {})
    except ValueError:
        e = {}
    m = f"{r.status_code}: {mesaj_platforma(r)}"
    if e.get("code") == 190 or r.status_code == 401:
        raise EroareAutentificare(m)
    if e.get("is_transient") or e.get("code") in CODURI_TEMPORARE:
        raise EroareTemporara(m)
    clasifica(r)


def procent_din_antete(antete: dict[str, str]) -> tuple[float | None, str]:
    """Procentul cel mai mare din antetele de utilizare Meta (fiecare valoare e JSON, uneori pe conturi)."""
    maxim, sursa = None, ""
    for nume in ANTETE_UTILIZARE:
        if nume not in antete:
            continue
        try:
            date = json.loads(antete[nume])
        except ValueError:
            continue
        valori = date.values() if isinstance(date, dict) else []
        for v in valori:
            for x in v if isinstance(v, list) else [v]:
                nums = x.values() if isinstance(x, dict) else [x]
                for n in nums:
                    if isinstance(n, int | float) and (maxim is None or n > maxim):
                        maxim, sursa = float(n), f"antetul {nume}"
    return maxim, sursa


class ConectorMeta:
    """Partea comună Facebook / Instagram: OAuth Meta, clientul Graph, limitele din antete."""

    canal = "meta"
    scopuri: tuple[str, ...] = SCOPURI_PAGINI

    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        versiune: str = "v23.0",
        depozit: DepozitTokenuri | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.app_id, self._secret, self.versiune = app_id, app_secret, versiune
        self.depozit = depozit or DepozitBaza()
        self.http = ClientHttp(f"{GRAPH}/{versiune}", transport, clasificator=clasifica_graph)

    @classmethod
    def din_setari(cls) -> "ConectorMeta":
        s = get_settings()
        return cls(
            app_id=s.meta_app_id,
            app_secret=s.meta_app_secret.get_secret_value(),
            versiune=s.meta_graph_versiune,
        )

    def _token(self, tenant_id: uuid.UUID) -> Token:
        return token_sau_autentificare(self.depozit, tenant_id, self.canal)

    def _cere(self, metoda: str, cale: str, token: Token, **kw: Any) -> dict[str, Any]:
        return dict(self.http.cere(metoda, cale, token=token, **kw).json())

    # --- autorizare -----------------------------------------------------------------------------------------
    def url_autorizare(self, stare: str, redirect: str) -> str:
        q = {
            "client_id": self.app_id,
            "redirect_uri": redirect,
            "state": stare,
            "scope": ",".join(self.scopuri),
            "response_type": "code",
        }
        return f"https://www.facebook.com/{self.versiune}/dialog/oauth?{urlencode(q)}"

    def _schimb(self, **date: str) -> dict[str, Any]:
        r = self.http.cere(
            "POST",
            "oauth/access_token",
            data={"client_id": self.app_id, "client_secret": self._secret, **date},
        )
        return dict(r.json())

    def _lung(self, scurt: str) -> dict[str, Any]:
        return self._schimb(grant_type="fb_exchange_token", fb_exchange_token=scurt)

    def schimba_cod(self, cod: str, redirect: str) -> Token:
        scurt = self._schimb(code=cod, redirect_uri=redirect)
        lung = self._lung(str(scurt["access_token"]))
        return self._din_lung(lung)

    def reimprospateaza(self, token: Token) -> Token:
        if not token.reimprospatare:
            raise EroareAutentificare("fără token lung de utilizator: reautorizare")
        return self._din_lung(self._lung(token.reimprospatare))

    def _din_lung(self, lung: dict[str, Any]) -> Token:
        utilizator = Token(str(lung["access_token"]))
        pagini = self._cere(
            "GET",
            "me/accounts",
            utilizator,
            params={"fields": "id,name,access_token,instagram_business_account"},
        )
        if not pagini.get("data"):
            raise EroareDefinitiva("contul nu administrează nicio pagină")
        p = pagini["data"][0]
        t = Token(str(p["access_token"]), None, utilizator.acces, self._cont_din(p), self.scopuri)
        return cu_expirare(t, lung.get("expires_in"))

    def _cont_din(self, pagina: dict[str, Any]) -> str:
        return str(pagina["id"])

    # --- limite ---------------------------------------------------------------------------------------------
    def limite(self, tenant_id: uuid.UUID) -> Limite:
        t = self._token(tenant_id)
        if not any(a in self.http.antete for a in ANTETE_UTILIZARE):
            self._cere("GET", t.cont_extern, t, params={"fields": "id"})
        procent, sursa = procent_din_antete(self.http.antete)
        return Limite(sursa or "antetele Graph (lipsă)", procent_folosit=procent)


class ConectorFacebook(ConectorMeta):
    canal = "facebook"

    def trimite(self, efect: EfectDeTrimis) -> RezultatPlatforma:
        t = self._token(efect.tenant_id)
        date = {"message": text_postare(efect.payload)}
        if efect.payload.get("link"):
            date["link"] = str(efect.payload["link"])
        r = self._cere("POST", f"{t.cont_extern}/feed", t, data=date)
        return RezultatPlatforma(str(r["id"]), self._permalink(t, str(r["id"])))

    def _permalink(self, t: Token, pid: str) -> str:
        r = self._cere("GET", pid, t, params={"fields": "permalink_url"})
        return str(r.get("permalink_url") or f"https://www.facebook.com/{pid}")

    def verifica(self, efect: EfectDeTrimis) -> RezultatPlatforma | None:
        t = self._token(efect.tenant_id)
        text = text_postare(efect.payload)
        r = self._cere(
            "GET",
            f"{t.cont_extern}/published_posts",
            t,
            params={"fields": "id,message,permalink_url", "limit": "25"},
        )
        for p in r.get("data", []):
            if p.get("message") == text:
                return RezultatPlatforma(str(p["id"]), str(p.get("permalink_url", "")))
        return None

    def stare(self, tenant_id: uuid.UUID, id_extern: str) -> StarePostare:
        t = self._token(tenant_id)
        r = self.http.cere(
            "GET", id_extern, token=t, params={"fields": "is_published"}, clasifica_erori=False
        )
        if r.status_code == 404 or (r.status_code == 400 and r.json().get("error", {}).get("code") == 100):
            return StarePostare.INEXISTENTA
        clasifica_graph(r)
        return StarePostare.PUBLICATA if r.json().get("is_published", True) else StarePostare.IN_PROCESARE
