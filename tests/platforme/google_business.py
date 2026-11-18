"""# SIMULAT: OAuth Google și Google Business Profile (`v4/.../localPosts`, conturi și locații), ca server HTTP
local. Postările noi sunt `LIVE`; textul care conține „interzis” iese `REJECTED` (politica de conținut)."""

import datetime as dt
import secrets
from typing import Any

import httpx

from tests.platforme.baza import PlatformaHttp

CLIENT_ID, CLIENT_SECRET = "ama-test.apps.googleusercontent.com", "gocspx-test"  # pragma: allowlist secret


class GoogleBusinessSimulat(PlatformaHttp):
    def __init__(self) -> None:
        super().__init__()
        self.cont, self.locatie = "accounts/112233", "locations/445566"

    @property
    def cont_extern(self) -> str:
        return f"{self.cont}/{self.locatie}"

    @staticmethod
    def eroare(cod: int, mesaj: str) -> httpx.Response:
        return httpx.Response(cod, json={"error": {"code": cod, "message": mesaj}})

    def trateaza(self, req: httpx.Request) -> httpx.Response:
        if req.url.host == "oauth2.googleapis.com":
            return self._token(self.corp(req))
        if not self.autorizat(req):
            return self.eroare(401, "Request had invalid authentication credentials.")
        cale = req.url.path
        if req.url.host.startswith("mybusinessaccountmanagement") and cale == "/v1/accounts":
            return self.json(200, {"accounts": [{"name": self.cont, "type": "LOCATION_GROUP"}]})
        if req.url.host.startswith("mybusinessbusinessinformation") and cale == f"/v1/{self.cont}/locations":
            return self.json(200, {"locations": [{"name": self.locatie, "title": "Cofetăria Zorilor"}]})
        baza = f"/v4/{self.cont_extern}/localPosts"
        if cale == baza and req.method == "POST":
            return self._publica(req, self.corp(req))
        if cale == baza:
            return self.json(200, {"localPosts": list(reversed(self.postari))})
        for p in self.postari:
            if cale == f"/v4/{p['name']}":
                return self.json(200, p)
        return self.eroare(404, "Requested entity was not found.")

    def _token(self, p: dict[str, Any]) -> httpx.Response:
        if p.get("client_id") != CLIENT_ID or p.get("client_secret") != CLIENT_SECRET:
            return self.json(401, {"error": "invalid_client"})
        if p.get("grant_type") == "refresh_token":
            if not str(p.get("refresh_token", "")).startswith("1//"):
                return self.json(400, {"error": "invalid_grant"})
            return self.json(200, {"access_token": self.token_nou("ya29"), "expires_in": 3599})
        if p.get("code") not in self.coduri:
            return self.json(400, {"error": "invalid_grant", "error_description": "Malformed auth code."})
        self.coduri.discard(p["code"])
        return self.json(200, {"access_token": self.token_nou("ya29"), "expires_in": 3599,
                               "refresh_token": "1//" + secrets.token_hex(8)})  # fmt: skip

    def _publica(self, req: httpx.Request, corp: dict[str, Any]) -> httpx.Response:
        d = self.defect()
        if d == "temporar":
            return self.eroare(503, "The service is currently unavailable.")
        if d == "timeout":
            return self.timeout(req)
        if d == "autentificare":
            return self.eroare(401, "Request had invalid authentication credentials.")
        if d == "definitiv" or not corp.get("summary") or corp.get("topicType") != "STANDARD":
            return self.eroare(400, "Request contains an invalid argument.")
        n = len(self.postari)
        p = {"name": f"{self.cont_extern}/localPosts/{9000 + n}", "summary": corp["summary"],
             "state": "REJECTED" if "interzis" in corp["summary"] else "LIVE",
             "createTime": dt.datetime.now(dt.UTC).isoformat(), "searchUrl": f"https://local.google.com/p/{9000 + n}"}  # fmt: skip
        self.postari.append(p)
        if d == "pierde_raspunsul":
            return self.timeout(req)
        return self.json(200, p)
