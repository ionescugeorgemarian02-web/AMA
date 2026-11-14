"""Punctul de intrare al aplicației web."""

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app import __version__, conturi, db, finante, panou, portal, site
from app.config import get_settings
from app.connectors.telegram.web import router as router_telegram
from app.logging import configure_logging, correlation_id, get_logger
from app.operare import backup, health, livrare
from app.operare.antete import adauga_antete
from app.operare.jurnale import ip_cerere

log = get_logger("app.http")


def create_app() -> FastAPI:
    settings = get_settings()
    settings.require_secrets()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="AMA",
        version=__version__,
        docs_url="/docs" if settings.env in ("dev", "test") else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.env in ("dev", "test") else None,
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-request-id", "")
        cid = (
            incoming
            if 8 <= len(incoming) <= 64 and incoming.isascii() and incoming.isprintable()
            else str(uuid.uuid4())
        )
        token = correlation_id.set(cid)
        ip_token = ip_cerere.set(request.client.host if request.client else None)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            if request.url.path not in ("/healthz", "/readyz"):
                log.info(
                    "cerere",
                    extra={"method": request.method, "path": request.url.path, "duration_ms": duration_ms},
                )
            correlation_id.reset(token)
            ip_cerere.reset(ip_token)
        response.headers["x-request-id"] = cid
        return response

    adauga_antete(app)
    health.register_check("baza", db.verifica_baza)
    # Backup-ul NU intră în /readyz (care deschide poarta livrărilor); are un indicator separat.
    health.register_indicator("backup", backup.indicator)
    app.include_router(health.router)
    conturi.inregistreaza(app)
    panou.inregistreaza(app)
    site.inregistreaza(app)  # /site: site-ul public (F7)
    portal.inregistreaza(app)  # /portal: portalul clientului (F7)
    app.include_router(finante.router)  # /facturare/webhook: semnat de procesatorul de plăți (F7.6)
    app.include_router(livrare.router)  # /intern/livrare/*: doar cu jeton, blocat în proxy
    app.include_router(router_telegram)  # /telegram/webhook: doar cu antetul-secret
    return app


app = create_app()
