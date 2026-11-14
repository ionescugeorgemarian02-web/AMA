"""# SIMULAT: OAuth Google și YouTube Data API v3 (încărcare reluabilă), ca server HTTP local. Proiectul
neauditat își vede clipurile blocate pe privat (ca platforma reală), oricare ar fi vizibilitatea cerută."""

import json
import secrets
from typing import Any

import httpx

from tests.platforme.baza import PlatformaHttp

CLIENT_ID, CLIENT_SECRET = "ama-test.apps.googleusercontent.com", "gocspx-test"  # pragma: allowlist secret


class YoutubeSimulat(PlatformaHttp):
    def __init__(self) -> None:
        super().__init__()
        self.auditat = False
        self.sesiuni: dict[str, dict[str, Any]] = {}
        self.reimprospatari: set[str] = set()

    @staticmethod
    def eroare(cod: int, motiv: str, mesaj: str) -> httpx.Response:
        return httpx.Response(
            cod, json={"error": {"code": cod, "message": mesaj, "errors": [{"reason": motiv}]}}
        )

    def trateaza(self, req: httpx.Request) -> httpx.Response:
        if req.url.host == "oauth2.googleapis.com":
            return self._token(self.corp(req))
        if not self.autorizat(req):
            return self.eroare(401, "authError", "Invalid Credentials")
        p, cale = dict(req.url.params), req.url.path
        if cale == "/youtube/v3/channels":
            return self.json(
                200,
                {
                    "items": [
                        {"id": "UCzorilor", "contentDetails": {"relatedPlaylists": {"uploads": "UUzorilor"}}}
                    ]
                },
            )
        if cale == "/upload/youtube/v3/videos" and req.method == "POST":
            return self._init(req, p)
        if cale == "/upload/youtube/v3/videos" and req.method == "PUT":
            return self._incarca(req, p)
        if cale == "/youtube/v3/playlistItems":
            return self.json(
                200,
                {
                    "items": [
                        {
                            "snippet": {
                                "title": v["titlu"],
                                "description": v["text"],
                                "resourceId": {"videoId": v["id"]},
                            }
                        }
                        for v in reversed(self.postari)
                    ]
                },
            )
        if cale == "/youtube/v3/videos":
            gasite = [v for v in self.postari if v["id"] == p.get("id")]
            return self.json(
                200,
                {
                    "items": [
                        {
                            "id": v["id"],
                            "status": {"uploadStatus": "processed", "privacyStatus": v["vizibilitate"]},
                        }
                        for v in gasite
                    ]
                },
            )
        return self.eroare(404, "notFound", "Not found")

    def _token(self, p: dict[str, Any]) -> httpx.Response:
        if p.get("client_id") != CLIENT_ID or p.get("client_secret") != CLIENT_SECRET:
            return self.json(401, {"error": "invalid_client"})
        if p.get("grant_type") == "refresh_token":
            if p.get("refresh_token") not in self.reimprospatari:
                return self.json(400, {"error": "invalid_grant"})
            return self.json(200, {"access_token": self.token_nou("ya29"), "expires_in": 3599})
        if p.get("code") not in self.coduri:
            return self.json(400, {"error": "invalid_grant", "error_description": "Bad Request"})
        self.coduri.discard(p["code"])
        r = "1//" + secrets.token_hex(8)
        self.reimprospatari.add(r)
        return self.json(
            200,
            {
                "access_token": self.token_nou("ya29"),
                "expires_in": 3599,
                "refresh_token": r,
                "scope": "youtube.upload youtube.readonly",
                "token_type": "Bearer",
            },
        )

    def _init(self, req: httpx.Request, p: dict[str, Any]) -> httpx.Response:
        if p.get("uploadType") != "resumable":
            return self.eroare(400, "badRequest", "uploadType")
        m = json.loads(req.content)
        s, st = m.get("snippet", {}), m.get("status", {})
        if not s.get("title") or "privacyStatus" not in st or "containsSyntheticMedia" not in st:
            return self.eroare(
                400, "invalidMetadata", "titlu, vizibilitate și declarația de conținut sintetic"
            )
        sid = secrets.token_hex(6)
        self.sesiuni[sid] = {"m": m, "lungime": int(req.headers.get("x-upload-content-length", "0"))}
        url = f"https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id={sid}"
        return httpx.Response(200, headers={"Location": url})

    def _incarca(self, req: httpx.Request, p: dict[str, Any]) -> httpx.Response:
        d = self.defect()
        if d == "temporar":
            return self.eroare(503, "backendError", "Backend Error")
        if d == "timeout":
            return self.timeout(req)
        if d == "autentificare":
            return self.eroare(401, "authError", "Invalid Credentials")
        if d == "definitiv":
            return self.eroare(400, "uploadLimitExceeded", "The user has exceeded the number of videos")
        ses = self.sesiuni.pop(str(p.get("upload_id")), None)
        if ses is None or len(req.content) != ses["lungime"]:
            return self.eroare(400, "badRequest", "sesiune de încărcare necunoscută")
        m = ses["m"]
        vid = "v" + secrets.token_hex(5)
        vizibilitate = m["status"]["privacyStatus"] if self.auditat else "private"
        self.postari.append(
            {
                "id": vid,
                "titlu": m["snippet"]["title"],
                "text": m["snippet"]["description"],
                "vizibilitate": vizibilitate,
                "sintetic": m["status"]["containsSyntheticMedia"],
            }
        )
        if d == "pierde_raspunsul":
            return self.timeout(req)
        return self.json(
            200, {"id": vid, "status": {"uploadStatus": "uploaded", "privacyStatus": vizibilitate}}
        )
