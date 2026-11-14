"""# SIMULAT: OAuth LinkedIn și Posts API (`/rest/posts`, Rest.li 2.0), ca server HTTP local. Cere antetele
`LinkedIn-Version` și `X-Restli-Protocol-Version`, întoarce urn-ul în `x-restli-id`."""

import json
import secrets
import time
from typing import Any
from urllib.parse import unquote

import httpx

from tests.platforme.baza import PlatformaHttp

CLIENT_ID, CLIENT_SECRET = "86ama-test", "WPL_AP1.test"  # pragma: allowlist secret


class LinkedinSimulat(PlatformaHttp):
    def __init__(self) -> None:
        super().__init__()
        self.persoana, self.organizatie = "urn:li:person:zorilor42", "urn:li:organization:777"

    @staticmethod
    def eroare(cod: int, mesaj: str) -> httpx.Response:
        return httpx.Response(cod, json={"status": cod, "message": mesaj})

    def trateaza(self, req: httpx.Request) -> httpx.Response:
        cale = req.url.path
        if req.url.host == "www.linkedin.com" and cale == "/oauth/v2/accessToken":
            return self._token(self.corp(req))
        if not self.autorizat(req):
            return self.eroare(401, "Invalid access token")
        if cale == "/v2/userinfo":
            return self.json(200, {"sub": self.persoana.rsplit(":", 1)[1], "name": "Cafeneaua Zorilor"})
        if cale.startswith("/rest/") and (
            req.headers.get("x-restli-protocol-version") != "2.0.0" or not req.headers.get("linkedin-version")
        ):
            return self.eroare(400, "lipsesc antetele de versiune")
        if cale == "/rest/organizationAcls":
            return self.json(
                200,
                {
                    "elements": [
                        {"organization": self.organizatie, "role": "ADMINISTRATOR", "state": "APPROVED"}
                    ]
                },
            )
        if cale == "/rest/posts" and req.method == "POST":
            return self._publica(req, json.loads(req.content))
        if cale == "/rest/posts":
            autor = req.url.params.get("author")
            return self.json(200, {"elements": [p for p in reversed(self.postari) if p["author"] == autor]})
        if cale.startswith("/rest/posts/"):
            urn = unquote(cale.removeprefix("/rest/posts/"))
            for p in self.postari:
                if p["id"] == urn:
                    return self.json(200, p)
            return self.eroare(404, "Not found")
        return self.eroare(404, "Not found")

    def _token(self, p: dict[str, Any]) -> httpx.Response:
        if p.get("client_id") != CLIENT_ID or p.get("client_secret") != CLIENT_SECRET:
            return self.json(401, {"error": "invalid_client"})
        if p.get("grant_type") == "refresh_token":
            if not str(p.get("refresh_token", "")).startswith("AQX"):
                return self.json(400, {"error": "invalid_grant"})
            return self.json(200, {"access_token": self.token_nou("AQV"), "expires_in": 5184000})
        if p.get("code") not in self.coduri:
            return self.json(
                400, {"error": "invalid_request", "error_description": "authorization code not found"}
            )
        self.coduri.discard(p["code"])
        return self.json(
            200,
            {
                "access_token": self.token_nou("AQV"),
                "expires_in": 5184000,
                "refresh_token": "AQX" + secrets.token_hex(6),
                "scope": "w_member_social",
            },
        )

    def _publica(self, req: httpx.Request, corp: dict[str, Any]) -> httpx.Response:
        d = self.defect()
        if d == "temporar":
            return self.eroare(503, "Service Unavailable")
        if d == "timeout":
            return self.timeout(req)
        if d == "autentificare":
            return self.eroare(401, "Expired access token")
        if (
            d == "definitiv"
            or not corp.get("commentary")
            or corp.get("author") not in (self.persoana, self.organizatie)
        ):
            return self.eroare(422, "ERROR :: /commentary :: invalid")
        urn = f"urn:li:share:{7000000000000000000 + len(self.postari)}"
        self.postari.append(
            {
                "id": urn,
                "author": corp["author"],
                "commentary": corp["commentary"],
                "lifecycleState": "PUBLISHED",
                "createdAt": int(time.time() * 1000),
            }
        )
        if d == "pierde_raspunsul":
            return self.timeout(req)
        return httpx.Response(201, headers={"x-restli-id": urn})
