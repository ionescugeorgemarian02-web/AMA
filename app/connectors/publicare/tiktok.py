"""Conectorul TikTok (F9.6): Content Posting API v2.

Două moduri, după starea auditului aplicației (`pachet["mod_tiktok"]`, pus de publicare din aprobare):
- **ciornă** (`inbox/video/init`): clipul ajunge în căsuța creatorului din aplicația TikTok; creatorul îl
  finalizează și îl publică de acolo. Modul de dinainte de audit (15.1).
- **postare directă** (`video/init`), după audit, cu regulile TikTok pentru integrări: înainte de fiecare
  postare se citesc opțiunile creatorului (`creator_info/query`), omul vede previzualizarea (pseudonimul
  contului, clipul, legenda), ALEGE vizibilitatea (fără valoare implicită) și interacțiunile, își dă
  consimțământul explicit; fără consimțământ în pachet sau cu o vizibilitate pe care creatorul nu o mai are,
  conectorul refuză (definitiv). Eticheta AI → `is_aigc`; conținutul comercial → comutatoarele de brand.
- Fișierul: `PULL_FROM_URL`, prin link semnat (`publicare.linkuri`); starea: `status/fetch` (pauze
  crescătoare, ceas injectat), până la `PUBLISH_COMPLETE` / `SEND_TO_USER_INBOX`.
- `verifica`: la postarea directă, lista clipurilor publice (`video/list`) după titlu; ciornele nu se pot
căuta
  (o ciornă dublă e inofensivă: o publică omul).
- Limita: postările de azi (`video/list`) față de plafonul zilnic al creatorului (`PLAFON_ZI` [I]).

# NEVERIFICAT: auditul, plafonul zilnic, timpii de procesare, ghidul UX TikTok pe aplicația reală; API
# simulat.
"""

import datetime as dt
import time
import uuid
from collections.abc import Callable
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

API = "https://open.tiktokapis.com"
SCOPURI = ("user.info.basic", "video.publish", "video.upload", "video.list")
PLAFON_ZI = 15  # [I] postări pe zi și creator
PASI_STARE = 12
COD_AUTENTIFICARE = {"access_token_invalid", "scope_not_authorized", "token_expired"}
COD_TEMPORAR = {"rate_limit_exceeded", "internal_error"}


def clasifica_tiktok(r: httpx.Response) -> None:
    try:
        e = r.json().get("error") or {}
        cod = str(e.get("code", "ok")) if isinstance(e, dict) else str(e)
    except (ValueError, AttributeError):
        cod = ""
    if r.status_code < 400 and cod in ("ok", ""):
        return
    m = f"{r.status_code}: {cod}: {mesaj_platforma(r)}"
    if cod in COD_AUTENTIFICARE:
        raise EroareAutentificare(m)
    if cod in COD_TEMPORAR:
        raise EroareTemporara(m)
    if r.status_code < 400:
        raise EroareDefinitiva(m)
    clasifica(r)


def adresa_fisier(cale: str) -> str:
    from app.publicare import linkuri

    return linkuri.semneaza(cale)


class ConectorTiktok:
    canal = "tiktok"

    def __init__(
        self,
        *,
        client_key: str,
        client_secret: str,
        depozit: DepozitTokenuri | None = None,
        transport: httpx.BaseTransport | None = None,
        dormi: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client_key, self._secret = client_key, client_secret
        self.depozit = depozit or DepozitBaza()
        self.http = ClientHttp(API, transport, clasificator=clasifica_tiktok)
        self.dormi = dormi

    @classmethod
    def din_setari(cls) -> "ConectorTiktok":
        s = get_settings()
        return cls(client_key=s.tiktok_client_key, client_secret=s.tiktok_client_secret.get_secret_value())

    def _token(self, tenant_id: uuid.UUID) -> Token:
        return token_sau_autentificare(self.depozit, tenant_id, self.canal)

    def _post(self, cale: str, t: Token, corp: dict[str, Any] | None = None) -> dict[str, Any]:
        r = self.http.cere(
            "POST",
            cale,
            token=t,
            json=corp or {},
            headers={"Content-Type": "application/json; charset=UTF-8"},
        )
        return dict(r.json().get("data") or {})

    # --- autorizare -----------------------------------------------------------------------------------------
    def url_autorizare(self, stare: str, redirect: str) -> str:
        q = {
            "client_key": self.client_key,
            "scope": ",".join(SCOPURI),
            "response_type": "code",
            "redirect_uri": redirect,
            "state": stare,
        }
        return f"https://www.tiktok.com/v2/auth/authorize/?{urlencode(q)}"

    def _schimb(self, **date: str) -> Token:
        r = self.http.cere(
            "POST",
            "v2/oauth/token/",
            data={"client_key": self.client_key, "client_secret": self._secret, **date},
        )
        d = r.json()
        if "access_token" not in d:
            raise EroareDefinitiva(f"TikTok a refuzat schimbul: {d.get('error', 'necunoscut')}")
        t = Token(
            str(d["access_token"]), None, str(d.get("refresh_token", "")), str(d.get("open_id", "")), SCOPURI
        )
        return cu_expirare(t, d.get("expires_in"))

    def schimba_cod(self, cod: str, redirect: str) -> Token:
        return self._schimb(code=cod, grant_type="authorization_code", redirect_uri=redirect)

    def reimprospateaza(self, token: Token) -> Token:
        if not token.reimprospatare:
            raise EroareAutentificare("fără token de reîmprospătare: reautorizare")
        return self._schimb(grant_type="refresh_token", refresh_token=token.reimprospatare)

    # --- previzualizarea (înainte de consimțământ) ----------------------------------------------------------
    def creator(self, tenant_id: uuid.UUID) -> dict[str, Any]:
        """Opțiunile creatorului, citite chiar înainte de previzualizare și de postare (regula TikTok)."""
        return self._post("v2/post/publish/creator_info/query/", self._token(tenant_id))

    # --- publicare ------------------------------------------------------------------------------------------
    @staticmethod
    def info_postare(payload: dict[str, Any], creator: dict[str, Any]) -> dict[str, Any]:
        """Nucleu pur: `post_info` din pachet și consimțământ; refuză ce încalcă regulile de integrare."""
        c = payload.get("consimtamant") or {}
        if not c.get("id") or not c.get("dat_de"):
            raise EroareDefinitiva(
                "postarea directă pe TikTok cere consimțământul explicit, după previzualizare"
            )
        nivel = c.get("vizibilitate")
        if nivel not in (creator.get("privacy_level_options") or []):
            raise EroareDefinitiva(
                f"vizibilitatea „{nivel}” nu mai este permisă contului: refă previzualizarea"
            )
        return {
            "title": text_postare(payload)[:2200],
            "privacy_level": nivel,
            "disable_comment": bool(c.get("fara_comentarii")) or bool(creator.get("comment_disabled")),
            "disable_duet": bool(c.get("fara_duet")) or bool(creator.get("duet_disabled")),
            "disable_stitch": bool(c.get("fara_stitch")) or bool(creator.get("stitch_disabled")),
            "brand_content_toggle": bool(payload.get("marcaj_comercial")),
            "brand_organic_toggle": False,
            "is_aigc": bool(payload.get("eticheta_ai")),
        }

    def trimite(self, efect: EfectDeTrimis) -> RezultatPlatforma:
        t = self._token(efect.tenant_id)
        fisier = str(efect.payload.get("fisier") or "")
        if not fisier:
            raise EroareDefinitiva("TikTok cere un fișier video")
        sursa = {"source": "PULL_FROM_URL", "video_url": adresa_fisier(fisier)}
        if efect.payload.get("mod_tiktok") == "direct":
            info = self.info_postare(efect.payload, self._post("v2/post/publish/creator_info/query/", t))
            d = self._post("v2/post/publish/video/init/", t, {"post_info": info, "source_info": sursa})
        else:
            d = self._post("v2/post/publish/inbox/video/init/", t, {"source_info": sursa})
        return self._asteapta(t, str(d["publish_id"]))

    def _asteapta(self, t: Token, publish_id: str) -> RezultatPlatforma:
        pauza = 1.0
        for _ in range(PASI_STARE):
            d = self._post("v2/post/publish/status/fetch/", t, {"publish_id": publish_id})
            s = d.get("status")
            if s == "PUBLISH_COMPLETE":
                ids = d.get("publicaly_available_post_id") or []
                link = f"https://www.tiktok.com/@{t.cont_extern}/video/{ids[0]}" if ids else ""
                return RezultatPlatforma(publish_id, link or "https://www.tiktok.com/")
            if s == "SEND_TO_USER_INBOX":
                return RezultatPlatforma(publish_id, "https://www.tiktok.com/tiktokstudio/content")
            if s == "FAILED":
                raise EroareDefinitiva(f"TikTok a respins clipul: {d.get('fail_reason', 'necunoscut')}")
            self.dormi(pauza)
            pauza = min(pauza * 2, 30.0)
        raise EroareTemporara("clipul încă se procesează la TikTok")

    def _clipuri(self, t: Token) -> list[dict[str, Any]]:
        r = self.http.cere(
            "POST",
            "v2/video/list/",
            token=t,
            params={"fields": "id,title,create_time,share_url"},
            json={"max_count": 20},
        )
        return list((r.json().get("data") or {}).get("videos") or [])

    def verifica(self, efect: EfectDeTrimis) -> RezultatPlatforma | None:
        t = self._token(efect.tenant_id)
        if efect.payload.get("mod_tiktok") != "direct":
            return None  # ciornele nu sunt căutabile; o ciornă dublă o vede și o decide omul
        titlu = text_postare(efect.payload)[:2200]
        for v in self._clipuri(t):
            if v.get("title") == titlu:
                return RezultatPlatforma(str(v.get("publish_id", v["id"])), str(v.get("share_url", "")))
        return None

    def stare(self, tenant_id: uuid.UUID, id_extern: str) -> StarePostare:
        d = self._post("v2/post/publish/status/fetch/", self._token(tenant_id), {"publish_id": id_extern})
        return {
            "PUBLISH_COMPLETE": StarePostare.PUBLICATA,
            "SEND_TO_USER_INBOX": StarePostare.CIORNA,
            "FAILED": StarePostare.ESUATA,
        }.get(str(d.get("status")), StarePostare.IN_PROCESARE)

    def limite(self, tenant_id: uuid.UUID) -> Limite:
        t = self._token(tenant_id)
        azi = dt.datetime.now(dt.UTC).date()
        n = sum(
            1
            for v in self._clipuri(t)
            if dt.datetime.fromtimestamp(int(v.get("create_time", 0)), dt.UTC).date() == azi
        )
        return Limite(
            "clipurile de azi citite din API, față de plafonul zilnic al creatorului",
            PLAFON_ZI - n,
            PLAFON_ZI,
        )
