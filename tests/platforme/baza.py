"""# SIMULAT: baza platformelor simulate. Fiecare platformă e un `httpx.MockTransport` care răspunde ca API-ul
real
(căi, parametri, coduri, forma erorilor), deci conectorul vorbește HTTP adevărat, fără rețea.

Defectele se injectează pe rând și se consumă la următoarea cerere de publicare: `temporar`, `timeout`,
`autentificare`, `definitiv`, `pierde_raspunsul` (publicarea se face, răspunsul se pierde)."""

import json
import secrets
from typing import Any

import httpx


class PlatformaHttp:
    def __init__(self) -> None:
        self.defecte: list[str] = []
        self.tokenuri: set[str] = set()
        self.coduri: set[str] = set()
        self.adrese: list[str] = []
        self.cereri: list[tuple[str, str]] = []
        self.postari: list[dict[str, Any]] = []

    # --- controlul testului ---------------------------------------------------------------------------------
    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._trateaza)

    def injecteaza(self, *defecte: str) -> None:
        self.defecte.extend(defecte)

    def postari_publicate(self) -> list[dict[str, Any]]:
        return list(self.postari)

    def expira_tokenul(self) -> None:
        self.tokenuri.clear()

    def cod_valid(self) -> str:
        c = "cod-" + secrets.token_hex(6)
        self.coduri.add(c)
        return c

    def token_nou(self, prefix: str = "tok") -> str:
        t = f"{prefix}-{secrets.token_hex(10)}"
        self.tokenuri.add(t)
        return t

    # --- ajutoare pentru rute -------------------------------------------------------------------------------
    def _trateaza(self, req: httpx.Request) -> httpx.Response:
        self.adrese.append(str(req.url))
        self.cereri.append((req.method, req.url.path))
        return self.trateaza(req)

    def trateaza(self, req: httpx.Request) -> httpx.Response:  # pragma: no cover - suprascris
        raise NotImplementedError

    def autorizat(self, req: httpx.Request) -> bool:
        a = req.headers.get("authorization", "")
        return a.startswith("Bearer ") and a[7:] in self.tokenuri

    def defect(self) -> str:
        return self.defecte.pop(0) if self.defecte else "ok"

    @staticmethod
    def corp(req: httpx.Request) -> dict[str, Any]:
        if not req.content:
            return {}
        ct = req.headers.get("content-type", "")
        if "json" in ct:
            return dict(json.loads(req.content))
        if "x-www-form-urlencoded" in ct:
            from urllib.parse import parse_qsl

            return dict(parse_qsl(req.content.decode()))
        return {}

    @staticmethod
    def json(cod: int, date: Any, **antete: str) -> httpx.Response:
        return httpx.Response(cod, json=date, headers=antete)

    @staticmethod
    def timeout(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulat", request=req)
