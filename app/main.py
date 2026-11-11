"""Punctul de intrare al aplicației web."""

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app import __version__
from app.config import get_settings
from app.logging import configure_logging, correlation_id, get_logger
from app.operare import health

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
        response.headers["x-request-id"] = cid
        return response

    app.include_router(health.router)
    return app


app = create_app()
