"""Antete de securitate (21.4): politică de conținut strictă, fără scripturi sau stiluri inline."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.config import get_settings

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
# Documentația interactivă (doar dev/test) încarcă scripturi de pe CDN și are cod inline.
CALE_DOCUMENTATIE = ("/docs", "/redoc", "/openapi.json")
HSTS = "max-age=63072000; includeSubDomains"


def adauga_antete(app: FastAPI) -> None:
    """Înregistrează middleware-ul. Mediul se citește o dată, la construirea aplicației."""
    dev = get_settings().env in ("dev", "test")

    @app.middleware("http")
    async def antete_securitate(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        h = response.headers
        if not (dev and request.url.path in CALE_DOCUMENTATIE):
            h["Content-Security-Policy"] = CSP
        h["X-Content-Type-Options"] = "nosniff"
        h["Referrer-Policy"] = "same-origin"
        h["X-Frame-Options"] = "DENY"
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        if not dev:
            h["Strict-Transport-Security"] = HSTS
        return response
