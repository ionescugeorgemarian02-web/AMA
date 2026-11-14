"""# SIMULAT: Graph API (Meta) pentru Facebook Pages și Instagram, ca server HTTP local. Formele urmează
documentația
publică Graph (erorile `{"error": {"code", "message", "type"}}`, codul 190 = token, antetul `X-App-Usage`).
Aplicația e „în modul de test”: răspunde doar conturilor agenției (`pagini_agentie`)."""

import json
import secrets
from typing import Any

import httpx

from tests.platforme.baza import PlatformaHttp

APP_ID, APP_SECRET = "app-test-ama", "secret-test-ama"  # pragma: allowlist secret


class GraphSimulat(PlatformaHttp):
    def __init__(self, pagina: str = "1001", ig: str = "17841400000000001") -> None:
        super().__init__()
        self.pagina, self.ig = pagina, ig
        self.apeluri = 0
        self.containere: dict[str, dict[str, Any]] = {}
        self.ig_media: list[dict[str, Any]] = []
        self.procesare_pasi = 2  # de câte ori containerul video răspunde IN_PROGRESS
        self.descarcate: list[str] = []  # adresele fișierelor aduse de Instagram
        self.descarca: Any = None  # funcția care aduce fișierul de la adresa semnată (testul o dă)
        self.limita_ig = 100

    # --- erori în forma Graph -------------------------------------------------------------------------------
    @staticmethod
    def eroare(cod_http: int, cod: int, mesaj: str, **extra: Any) -> httpx.Response:
        return httpx.Response(
            cod_http, json={"error": {"message": mesaj, "type": "OAuthException", "code": cod, **extra}}
        )

    def _defect_publicare(self, req: httpx.Request) -> httpx.Response | str:
        d = self.defect()
        if d == "temporar":
            return self.eroare(500, 2, "Service temporarily unavailable", is_transient=True)
        if d == "timeout":
            return self.timeout(req)
        if d == "autentificare":
            return self.eroare(400, 190, "Error validating access token: Session has expired")
        if d == "definitiv":
            return self.eroare(400, 100, "Invalid parameter")
        return d

    def _antete(self) -> dict[str, str]:
        self.apeluri += 1
        return {
            "X-App-Usage": json.dumps(
                {"call_count": min(100, self.apeluri), "total_time": 1, "total_cputime": 1}
            )
        }

    # --- rute -----------------------------------------------------------------------------------------------
    def trateaza(self, req: httpx.Request) -> httpx.Response:
        cale = req.url.path.split("/", 2)[-1] if req.url.path.count("/") >= 2 else req.url.path
        p = dict(req.url.params) | self.corp(req)
        if cale == "oauth/access_token":
            return self._token(p)
        if not self.autorizat(req):
            return self.eroare(400, 190, "Invalid OAuth access token.")
        r = self._ruta(req, cale, p)
        for k, v in self._antete().items():
            r.headers[k] = v
        return r

    def _token(self, p: dict[str, Any]) -> httpx.Response:
        if p.get("client_id") != APP_ID or p.get("client_secret") != APP_SECRET:
            return self.eroare(400, 101, "Error validating application")
        if p.get("grant_type") == "fb_exchange_token":
            if p.get("fb_exchange_token") not in self.tokenuri:
                return self.eroare(400, 190, "Invalid OAuth access token.")
            return self.json(
                200, {"access_token": self.token_nou("EAAL"), "token_type": "bearer", "expires_in": 5184000}
            )
        if p.get("code") not in self.coduri:
            return self.eroare(400, 100, "Invalid verification code format.")
        self.coduri.discard(p["code"])
        return self.json(
            200, {"access_token": self.token_nou("EAAs"), "token_type": "bearer", "expires_in": 3600}
        )

    def _ruta(self, req: httpx.Request, cale: str, p: dict[str, Any]) -> httpx.Response:
        m = req.method
        if cale == "me/accounts":
            return self.json(
                200,
                {
                    "data": [
                        {
                            "id": self.pagina,
                            "name": "Cafeneaua Zorilor",
                            "access_token": self.token_nou("EAAP"),
                            "instagram_business_account": {"id": self.ig},
                        }
                    ]
                },
            )
        if cale == f"{self.pagina}/feed" and m == "POST":
            return self._publica_fb(req, p)
        if cale == f"{self.pagina}/published_posts":
            return self.json(
                200,
                {
                    "data": [
                        {"id": x["id"], "message": x["text"], "permalink_url": x["link"]}
                        for x in reversed(self.postari)
                    ]
                },
            )
        if cale == self.pagina:
            return self.json(200, {"id": self.pagina, "name": "Cafeneaua Zorilor"})
        if cale.startswith(self.ig):
            return self._ig(req, cale, p)
        for x in self.ig_media:
            if cale == x["id"]:
                return self.json(200, {"id": x["id"], "permalink": x["link"], "media_type": x["tip"]})
        for x in self.postari:
            if cale == x["id"]:
                return self.json(200, {"id": x["id"], "is_published": True, "permalink_url": x["link"]})
        for c_id, c in self.containere.items():
            if cale == c_id:
                return self._container(c_id, c)
        return self.eroare(404, 100, "Unsupported get request. Object does not exist")

    def _publica_fb(self, req: httpx.Request, p: dict[str, Any]) -> httpx.Response:
        d = self._defect_publicare(req)
        if isinstance(d, httpx.Response):
            return d
        if not p.get("message"):
            return self.eroare(400, 100, "(#100) Missing message or attachment")
        pid = f"{self.pagina}_{secrets.randbelow(10**12)}"
        self.postari.append({"id": pid, "text": p["message"], "link": f"https://www.facebook.com/{pid}"})
        if d == "pierde_raspunsul":
            return self.timeout(req)
        return self.json(200, {"id": pid})

    # --- Instagram (F9.3) -----------------------------------------------------------------------------------
    def _ig(self, req: httpx.Request, cale: str, p: dict[str, Any]) -> httpx.Response:
        if cale == f"{self.ig}/content_publishing_limit":
            return self.json(
                200,
                {
                    "data": [
                        {
                            "quota_usage": len(self.ig_media),
                            "config": {"quota_total": self.limita_ig, "quota_duration": 86400},
                        }
                    ]
                },
            )
        if cale == f"{self.ig}/media" and req.method == "GET":
            return self.json(
                200,
                {
                    "data": [
                        {"id": m["id"], "caption": m["text"], "permalink": m["link"]}
                        for m in reversed(self.ig_media)
                    ]
                },
            )
        if cale == f"{self.ig}/media":
            return self._container_nou(p)
        if cale == f"{self.ig}/media_publish":
            return self._publica_ig(req, p)
        return self.eroare(404, 100, "Unsupported request")

    def _container_nou(self, p: dict[str, Any]) -> httpx.Response:
        url = p.get("video_url") if p.get("media_type") == "REELS" else p.get("image_url")
        if not url or not p.get("caption"):
            return self.eroare(400, 100, "(#100) The parameter image_url or video_url is required")
        if "access_token" in url:
            return self.eroare(400, 100, "token în adresa fișierului")
        if self.descarca is not None:
            cod = self.descarca(url)
            if cod != 200:
                return self.eroare(400, 9004, "Media download has failed.", error_subcode=2207052)
        self.descarcate.append(url)
        cid = str(17900000000000000 + len(self.containere))
        video = p.get("media_type") == "REELS"
        self.containere[cid] = {
            "text": p["caption"],
            "tip": "VIDEO" if video else "IMAGE",
            "ramas": self.procesare_pasi if video else 0,
        }
        return self.json(200, {"id": cid})

    def _container(self, c_id: str, c: dict[str, Any]) -> httpx.Response:
        if c["ramas"] > 0:
            c["ramas"] -= 1
            return self.json(200, {"id": c_id, "status_code": "IN_PROGRESS"})
        return self.json(200, {"id": c_id, "status_code": "FINISHED"})

    def _publica_ig(self, req: httpx.Request, p: dict[str, Any]) -> httpx.Response:
        d = self._defect_publicare(req)
        if isinstance(d, httpx.Response):
            return d
        c = self.containere.get(str(p.get("creation_id")))
        if c is None or c["ramas"] > 0:
            return self.eroare(400, 9007, "Media ID is not available", error_subcode=2207027)
        if len(self.ig_media) >= self.limita_ig:
            return self.eroare(400, 4, "Application request limit reached")
        mid = str(18000000000000000 + len(self.ig_media))
        m = {
            "id": mid,
            "text": c["text"],
            "tip": c["tip"],
            "link": f"https://www.instagram.com/p/C{mid[-8:]}/",
        }
        self.ig_media.append(m)
        self.postari.append(m)
        if d == "pierde_raspunsul":
            return self.timeout(req)
        return self.json(200, {"id": mid})
