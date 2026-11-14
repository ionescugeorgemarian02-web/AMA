"""# SIMULAT: WordPress REST API v2 (`/wp-json/wp/v2/posts`), ca server HTTP local, cu parolă de aplicație
(Basic)."""

import base64
import json
from typing import Any

import httpx

from tests.platforme.baza import PlatformaHttp

SITE = "https://cafeneauazorilor.example"


class WordpressSimulat(PlatformaHttp):
    def __init__(self) -> None:
        super().__init__()
        self.parole: set[str] = set()

    def parola_noua(self) -> str:
        p = "cafenea:" + " ".join(["abcd"] * 6)  # pragma: allowlist secret
        self.parole.add(p)
        self.tokenuri.add(p)
        return p

    def expira_tokenul(self) -> None:
        self.parole.clear()

    def autorizat(self, req: httpx.Request) -> bool:
        a = req.headers.get("authorization", "")
        return a.startswith("Basic ") and base64.b64decode(a[6:]).decode() in self.parole

    def trateaza(self, req: httpx.Request) -> httpx.Response:
        if not self.autorizat(req):
            return self.json(401, {"code": "rest_not_logged_in", "message": "Nu ești autentificat."})
        cale = req.url.path
        if cale == "/wp-json/wp/v2/posts" and req.method == "POST":
            return self._publica(req, json.loads(req.content))
        if cale == "/wp-json/wp/v2/posts":
            slug = req.url.params.get("slug")
            return self.json(200, [p for p in self.postari if p["slug"] == slug])
        if cale.startswith("/wp-json/wp/v2/posts/"):
            for p in self.postari:
                if str(p["id"]) == cale.rsplit("/", 1)[1]:
                    return self.json(200, p)
        return self.json(404, {"code": "rest_post_invalid_id"})

    def _publica(self, req: httpx.Request, c: dict[str, Any]) -> httpx.Response:
        d = self.defect()
        if d == "temporar":
            return self.json(503, {"code": "unavailable"})
        if d == "timeout":
            return self.timeout(req)
        if d == "autentificare":
            return self.json(401, {"code": "rest_not_logged_in"})
        if d == "definitiv" or not c.get("title") or c.get("status") != "publish":
            return self.json(400, {"code": "rest_invalid_param", "message": "Parametru invalid."})
        p = {
            "id": 100 + len(self.postari),
            "slug": c["slug"],
            "status": "publish",
            "title": c["title"],
            "content": c["content"],
            "text": c["title"],
            "link": f"{SITE}/{c['slug']}/",
        }
        self.postari.append(p)
        if d == "pierde_raspunsul":
            return self.timeout(req)
        return self.json(201, p)
