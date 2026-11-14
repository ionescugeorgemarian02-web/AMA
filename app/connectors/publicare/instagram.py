"""Conectorul Instagram (cont profesional, F9.3): Graph API, publicare în doi pași.

- Autorizarea: aceeași ca la Facebook (Meta), cu permisiunile Instagram; contul extern e
  `instagram_business_account` al paginii.
- Fișierul nu se încarcă: Instagram îl aduce de la o adresă publică. Adresa e un link semnat care expiră
  (`publicare.linkuri`), servit de platformă.
- Publicarea: `POST /{ig}/media` (imagine: `image_url`; clip: `media_type=REELS`, `video_url`) → container;
  pentru clip se citește `status_code` până la `FINISHED` (pauze crescătoare, cel mult `PASI_PROCESARE`); apoi
  `POST /{ig}/media_publish` și `permalink`.
- Limita: citită din endpoint (`content_publishing_limit`: `quota_usage` și `config.quota_total`), înainte de
  fiecare publicare (15.1: „100 de postări API în 24 h, de verificat în endpoint”). Epuizată → temporară.
- `verifica`: legenda exactă printre media recente ale contului.

# NEVERIFICAT: limitele reale, timpii de procesare a clipurilor, formatul REELS pe cont real; Graph simulat.
"""

import time
import uuid
from collections.abc import Callable
from typing import Any

from app.connectors.contract import EfectDeTrimis, Limite, RezultatPlatforma, StarePostare, Token
from app.connectors.publicare.baza import text_postare
from app.connectors.publicare.facebook import ConectorMeta, clasifica_graph
from app.operare.motor import EroareDefinitiva, EroareTemporara

SCOPURI_INSTAGRAM = (
    "instagram_basic",
    "instagram_content_publish",
    "pages_show_list",
    "pages_read_engagement",
)
PASI_PROCESARE = 12


def adresa_fisier(cale: str) -> str:
    from app.publicare import linkuri  # la execuție

    return linkuri.semneaza(cale)


class ConectorInstagram(ConectorMeta):
    canal = "instagram"
    scopuri = SCOPURI_INSTAGRAM

    def __init__(self, *, dormi: Callable[[float], None] = time.sleep, **kw: Any) -> None:
        super().__init__(**kw)
        self.dormi = dormi

    def _cont_din(self, pagina: dict[str, Any]) -> str:
        ig = pagina.get("instagram_business_account") or {}
        if not ig.get("id"):
            raise EroareDefinitiva("pagina nu are un cont Instagram profesional legat")
        return str(ig["id"])

    def limite(self, tenant_id: uuid.UUID) -> Limite:
        t = self._token(tenant_id)
        r = self._cere(
            "GET", f"{t.cont_extern}/content_publishing_limit", t, params={"fields": "quota_usage,config"}
        )
        d = (r.get("data") or [{}])[0]
        folosite, total = int(d.get("quota_usage", 0)), (d.get("config") or {}).get("quota_total")
        return Limite(
            "endpointul content_publishing_limit",
            None if total is None else int(total) - folosite,
            None if total is None else int(total),
        )

    def _container(self, t: Token, payload: dict[str, Any]) -> str:
        fisier = str(payload.get("fisier") or "")
        if not fisier:
            raise EroareDefinitiva("Instagram cere un fișier (imagine sau clip)")
        date = {"caption": text_postare(payload)}
        if payload.get("tip_media") == "video":
            date |= {"media_type": "REELS", "video_url": adresa_fisier(fisier)}
        else:
            date |= {"image_url": adresa_fisier(fisier)}
        return str(self._cere("POST", f"{t.cont_extern}/media", t, data=date)["id"])

    def _asteapta(self, t: Token, container: str) -> None:
        pauza = 1.0
        for _ in range(PASI_PROCESARE):
            stare = self._cere("GET", container, t, params={"fields": "status_code"}).get("status_code")
            if stare in ("FINISHED", "PUBLISHED"):
                return
            if stare in ("ERROR", "EXPIRED"):
                raise EroareDefinitiva(f"Instagram nu a putut procesa fișierul ({stare})")
            self.dormi(pauza)
            pauza = min(pauza * 2, 30.0)
        raise EroareTemporara("containerul încă se procesează")

    def trimite(self, efect: EfectDeTrimis) -> RezultatPlatforma:
        t = self._token(efect.tenant_id)
        lim = self.limite(efect.tenant_id)
        if lim.ramase is not None and lim.ramase <= 0:
            raise EroareTemporara("limita de publicare Instagram pe 24 h este atinsă")
        container = self._container(t, efect.payload)
        if efect.payload.get("tip_media") == "video":
            self._asteapta(t, container)
        mid = str(
            self._cere("POST", f"{t.cont_extern}/media_publish", t, data={"creation_id": container})["id"]
        )
        link = self._cere("GET", mid, t, params={"fields": "permalink"}).get("permalink")
        return RezultatPlatforma(mid, str(link or f"https://www.instagram.com/p/{mid}/"))

    def verifica(self, efect: EfectDeTrimis) -> RezultatPlatforma | None:
        t = self._token(efect.tenant_id)
        text = text_postare(efect.payload)
        r = self._cere(
            "GET", f"{t.cont_extern}/media", t, params={"fields": "id,caption,permalink", "limit": "25"}
        )
        for m in r.get("data", []):
            if m.get("caption") == text:
                return RezultatPlatforma(str(m["id"]), str(m.get("permalink", "")))
        return None

    def stare(self, tenant_id: uuid.UUID, id_extern: str) -> StarePostare:
        t = self._token(tenant_id)
        r = self.http.cere("GET", id_extern, token=t, params={"fields": "id"}, clasifica_erori=False)
        if r.status_code in (400, 404) and r.json().get("error", {}).get("code") == 100:
            return StarePostare.INEXISTENTA
        clasifica_graph(r)
        return StarePostare.PUBLICATA
