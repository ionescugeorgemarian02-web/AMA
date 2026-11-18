"""# SIMULAT: OAuth Threads și Threads API (containere, `threads_publish`, limita de publicare), ca server HTTP
local, cu forma erorilor Graph."""

from typing import Any

import httpx

from tests.platforme.baza import PlatformaHttp

APP_ID, APP_SECRET = "1234567890", "threads-secret-test"  # pragma: allowlist secret
COTA = 250


class ThreadsSimulat(PlatformaHttp):
    def __init__(self) -> None:
        super().__init__()
        self.utilizator = "17841400000000001"
        self.containere: dict[str, str] = {}

    @staticmethod
    def eroare(cod: int, mesaj: str, tip: str = "OAuthException", code: int = 100) -> httpx.Response:
        return httpx.Response(cod, json={"error": {"message": mesaj, "type": tip, "code": code}})

    def trateaza(self, req: httpx.Request) -> httpx.Response:
        cale = req.url.path
        if cale == "/oauth/access_token":
            return self._cod(self.corp(req))
        if not self.autorizat(req):
            return self.eroare(401, "Error validating access token", code=190)
        if cale == "/access_token":
            if req.url.params.get("client_secret") != APP_SECRET:
                return self.eroare(400, "Invalid client secret")
            return self.json(200, {"access_token": self.token_nou("THL"), "expires_in": 5183944})
        if cale == "/refresh_access_token":
            return self.json(200, {"access_token": self.token_nou("THL"), "expires_in": 5183944})
        if cale == "/v1.0/me":
            return self.json(200, {"id": self.utilizator})
        baza = f"/v1.0/{self.utilizator}"
        if cale == f"{baza}/threads" and req.method == "POST":
            return self._container(self.corp(req))
        if cale == f"{baza}/threads_publish":
            return self._publica(req, self.corp(req))
        if cale == f"{baza}/threads":
            return self.json(200, {"data": list(reversed(self.postari))})
        if cale == f"{baza}/threads_publishing_limit":
            return self.json(
                200, {"data": [{"quota_usage": len(self.postari), "config": {"quota_total": COTA}}]}
            )
        for p in self.postari:
            if cale == f"/v1.0/{p['id']}":
                return self.json(200, p)
        return self.eroare(400, "Object does not exist")

    def _cod(self, p: dict[str, Any]) -> httpx.Response:
        if p.get("client_id") != APP_ID or p.get("client_secret") != APP_SECRET:
            return self.eroare(400, "Invalid client")
        if p.get("code") not in self.coduri:
            return self.eroare(400, "Invalid authorization code")
        self.coduri.discard(p["code"])
        return self.json(200, {"access_token": self.token_nou("THS"), "user_id": self.utilizator})

    def _container(self, corp: dict[str, Any]) -> httpx.Response:
        if corp.get("media_type") != "TEXT" or not corp.get("text"):
            return self.eroare(400, "Invalid parameter")
        cid = f"c{len(self.containere)}"
        self.containere[cid] = str(corp["text"])
        return self.json(200, {"id": cid})

    def _publica(self, req: httpx.Request, corp: dict[str, Any]) -> httpx.Response:
        d = self.defect()
        if d == "temporar":
            return self.eroare(500, "An unknown error has occurred.", code=1)
        if d == "timeout":
            return self.timeout(req)
        if d == "autentificare":
            return self.eroare(401, "Error validating access token", code=190)
        text = self.containere.pop(str(corp.get("creation_id")), None)
        if d == "definitiv" or text is None:
            return self.eroare(400, "Invalid parameter")
        mid = str(18000000000000000 + len(self.postari))
        self.postari.append(
            {"id": mid, "text": text, "permalink": f"https://www.threads.net/@cofetaria/post/{mid}"}
        )
        if d == "pierde_raspunsul":
            return self.timeout(req)
        return self.json(200, {"id": mid})
