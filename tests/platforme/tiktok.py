"""# SIMULAT: OAuth TikTok și Content Posting API v2, ca server HTTP local. Aplicația neauditată poate posta
doar privat (`SELF_ONLY`); ciornele ajung în căsuța creatorului (`SEND_TO_USER_INBOX`)."""

import json
import secrets
import time
from typing import Any

import httpx

from tests.platforme.baza import PlatformaHttp

CLIENT_KEY, CLIENT_SECRET = "awama-test", "tt-secret-test"  # pragma: allowlist secret
TOATE = ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"]


class TiktokSimulat(PlatformaHttp):
    def __init__(self) -> None:
        super().__init__()
        self.auditat = False
        self.publicari: dict[str, dict[str, Any]] = {}
        self.ciorne: list[dict[str, Any]] = []
        self.procesare_pasi = 1
        self.descarca: Any = None

    @staticmethod
    def raspuns(
        cod_http: int, data: dict[str, Any] | None = None, cod: str = "ok", mesaj: str = ""
    ) -> httpx.Response:
        return httpx.Response(
            cod_http,
            json={
                "data": data or {},
                "error": {"code": cod, "message": mesaj, "log_id": secrets.token_hex(4)},
            },
        )

    def trateaza(self, req: httpx.Request) -> httpx.Response:
        cale = req.url.path
        if cale == "/v2/oauth/token/":
            return self._token(self.corp(req))
        if not self.autorizat(req):
            return self.raspuns(401, cod="access_token_invalid", mesaj="The access token is invalid")
        corp = json.loads(req.content) if req.content else {}
        if cale == "/v2/post/publish/creator_info/query/":
            return self.raspuns(
                200,
                {
                    "creator_username": "cafeneauazorilor",
                    "creator_nickname": "Cafeneaua Zorilor",
                    "privacy_level_options": TOATE if self.auditat else ["SELF_ONLY"],
                    "comment_disabled": False,
                    "duet_disabled": False,
                    "stitch_disabled": True,
                    "max_video_post_duration_sec": 600,
                },
            )
        if cale in ("/v2/post/publish/video/init/", "/v2/post/publish/inbox/video/init/"):
            return self._init(req, corp, directa=cale == "/v2/post/publish/video/init/")
        if cale == "/v2/post/publish/status/fetch/":
            return self._stare(str(corp.get("publish_id")))
        if cale == "/v2/video/list/":
            return self.raspuns(200, {"videos": list(reversed(self.postari)), "has_more": False})
        return self.raspuns(404, cod="not_found")

    def _token(self, p: dict[str, Any]) -> httpx.Response:
        if p.get("client_key") != CLIENT_KEY or p.get("client_secret") != CLIENT_SECRET:
            return self.json(400, {"error": "invalid_client"})
        if p.get("grant_type") == "refresh_token":
            if not str(p.get("refresh_token", "")).startswith("rft."):
                return self.json(400, {"error": "invalid_grant"})
        elif p.get("code") not in self.coduri:
            return self.json(
                400, {"error": "invalid_grant", "error_description": "Authorization code is expired."}
            )
        self.coduri.discard(str(p.get("code")))
        return self.json(
            200,
            {
                "access_token": self.token_nou("act"),
                "expires_in": 86400,
                "open_id": "cafeneauazorilor",
                "refresh_token": "rft." + secrets.token_hex(6),
                "refresh_expires_in": 31536000,
                "scope": "video.publish,video.upload",
                "token_type": "Bearer",
            },
        )

    def _init(self, req: httpx.Request, corp: dict[str, Any], *, directa: bool) -> httpx.Response:
        d = self.defect()
        if d == "temporar":
            return self.raspuns(500, cod="internal_error")
        if d == "timeout":
            return self.timeout(req)
        if d == "autentificare":
            return self.raspuns(401, cod="access_token_invalid")
        if d == "definitiv":
            return self.raspuns(400, cod="invalid_params", mesaj="spam risk")
        url = (corp.get("source_info") or {}).get("video_url", "")
        if "/publicare/fisier/" not in url:
            return self.raspuns(400, cod="invalid_params", mesaj="video_url")
        if self.descarca is not None and self.descarca(url) != 200:
            return self.raspuns(400, cod="url_ownership_unverified")
        pid = f"v_pub_url~v2.{secrets.randbelow(10**12)}"
        p: dict[str, Any] = {"ramas": self.procesare_pasi, "directa": directa}
        if directa:
            info = corp.get("post_info") or {}
            optiuni = TOATE if self.auditat else ["SELF_ONLY"]
            if info.get("privacy_level") not in optiuni:
                return self.raspuns(403, cod="unaudited_client_can_only_post_to_private_accounts")
            if "is_aigc" not in info or "brand_content_toggle" not in info:
                return self.raspuns(400, cod="invalid_params", mesaj="post_info incomplet")
            post_id = str(7400000000000000000 + len(self.postari))
            p |= {"post_id": post_id}
            self.postari.append(
                {
                    "id": post_id,
                    "publish_id": pid,
                    "title": info.get("title", ""),
                    "privacy": info["privacy_level"],
                    "is_aigc": info["is_aigc"],
                    "create_time": int(time.time()),
                    "share_url": f"https://www.tiktok.com/@cafeneauazorilor/video/{post_id}",
                }
            )
        else:
            self.ciorne.append({"publish_id": pid})
        self.publicari[pid] = p
        if d == "pierde_raspunsul":
            return self.timeout(req)
        return self.raspuns(200, {"publish_id": pid})

    def _stare(self, pid: str) -> httpx.Response:
        p = self.publicari.get(pid)
        if p is None:
            return self.raspuns(400, cod="invalid_publish_id")
        if p["ramas"] > 0:
            p["ramas"] -= 1
            return self.raspuns(200, {"status": "PROCESSING_DOWNLOAD"})
        if p["directa"]:
            return self.raspuns(
                200, {"status": "PUBLISH_COMPLETE", "publicaly_available_post_id": [p["post_id"]]}
            )
        return self.raspuns(200, {"status": "SEND_TO_USER_INBOX"})
