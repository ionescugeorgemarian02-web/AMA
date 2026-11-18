"""# SIMULAT: OAuth Pinterest și API v5 (`/v5/pins`, `/v5/boards`), ca server HTTP local. Schimbul codului cere
autentificare Basic; fiecare răspuns poartă antetele `x-ratelimit-*`."""

import base64
import secrets
from typing import Any

import httpx

from tests.platforme.baza import PlatformaHttp

CLIENT_ID, CLIENT_SECRET = "1490000", "pin-secret-test"  # pragma: allowlist secret
LIMITA = 1000


class PinterestSimulat(PlatformaHttp):
    def __init__(self) -> None:
        super().__init__()
        self.panou = "9876543210"

    def r(self, cod: int, date: Any) -> httpx.Response:
        folosite = len(self.cereri)
        return self.json(
            cod, date, **{"x-ratelimit-limit": str(LIMITA), "x-ratelimit-remaining": str(LIMITA - folosite)}
        )

    def eroare(self, cod: int, mesaj: str) -> httpx.Response:
        return self.r(cod, {"code": cod, "message": mesaj})

    def trateaza(self, req: httpx.Request) -> httpx.Response:
        cale = req.url.path
        if cale == "/v5/oauth/token":
            return self._token(req)
        if not self.autorizat(req):
            return self.eroare(401, "Authentication failed.")
        if cale == "/v5/boards":
            return self.r(200, {"items": [{"id": self.panou, "name": "Oferte"}]})
        if cale == "/v5/user_account":
            return self.r(200, {"username": "cofetariazorilor", "account_type": "BUSINESS"})
        if cale == "/v5/pins" and req.method == "POST":
            return self._publica(req, self.corp(req))
        if cale == f"/v5/boards/{self.panou}/pins":
            return self.r(200, {"items": list(reversed(self.postari)), "bookmark": None})
        if cale.startswith("/v5/pins/"):
            pid = cale.removeprefix("/v5/pins/")
            for p in self.postari:
                if p["id"] == pid:
                    return self.r(200, p)
        return self.eroare(404, "Not found.")

    def _token(self, req: httpx.Request) -> httpx.Response:
        asteptat = "Basic " + base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        if req.headers.get("authorization") != asteptat:
            return self.eroare(401, "invalid_client")
        p = self.corp(req)
        if p.get("grant_type") == "refresh_token":
            if not str(p.get("refresh_token", "")).startswith("pinr_"):
                return self.eroare(400, "invalid_grant")
        elif p.get("code") not in self.coduri:
            return self.eroare(400, "invalid_grant: authorization code not found")
        self.coduri.discard(str(p.get("code")))
        return self.r(200, {"access_token": self.token_nou("pina"), "expires_in": 2592000,
                            "refresh_token": "pinr_" + secrets.token_hex(6), "token_type": "bearer"})  # fmt: skip

    def _publica(self, req: httpx.Request, corp: dict[str, Any]) -> httpx.Response:
        d = self.defect()
        if d == "temporar":
            return self.eroare(503, "Service unavailable.")
        if d == "timeout":
            return self.timeout(req)
        if d == "autentificare":
            return self.eroare(401, "Authentication failed.")
        media = corp.get("media_source") or {}
        if d == "definitiv" or corp.get("board_id") != self.panou or not media.get("url"):
            return self.eroare(400, "Invalid parameters.")
        pin = {"id": str(1100000000000 + len(self.postari)), "board_id": corp["board_id"],
               "title": corp.get("title"), "description": corp.get("description"), "link": corp.get("link")}  # fmt: skip
        self.postari.append(pin)
        if d == "pierde_raspunsul":
            return self.timeout(req)
        return self.r(201, pin)
