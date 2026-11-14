"""Site-ul public al agenției (F7, docs/19 §19.1): paginile, blogul, analiza proprie cu acord.

from app import site
site.inregistreaza(app)          # rutele /site/*
site.blog.publica(db, ...)       # un articol pe blog (contextul de agenție)
"""

from fastapi import FastAPI

from app.site import analiza, audit, blog, motor_audit, pagini
from app.site.audit_web import router as router_audit
from app.site.captare_web import router as router_captare
from app.site.inscriere_web import router as router_inscriere
from app.site.web import router


def inregistreaza(app: FastAPI) -> None:
    app.include_router(router_audit)  # înaintea rutei generice a paginilor
    app.include_router(router_inscriere)
    app.include_router(router_captare)
    app.include_router(router)


__all__ = ["analiza", "audit", "blog", "inregistreaza", "motor_audit", "pagini", "router"]
