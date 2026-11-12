"""Panoul de control: coaja instalabilă (F1.7), Operare (partea din panou pentru F1.8/F1.9) și rutele PWA.

Cum adaugi un ecran: o rută în `web.py` cu dependența `Agentie`, un șablon în `app/web/templates/panou/` care
extinde `panou/baza.html`, și, dacă e una dintre cele cinci file, un rând în lista din `baza.html`.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.panou.alerte_web import router as router_alerte
from app.panou.aprobari_web import router as router_aprobari
from app.panou.motor_web import router as router_motor
from app.panou.operare_web import router as router_operare
from app.panou.productie_web import router as router_productie
from app.panou.sabloane import STATIC
from app.panou.web import router


class StaticCuRevalidare(StaticFiles):
    """Statice: cele vendorizate (nume cu versiune) se țin mult; restul se revalidează la fiecare cerere."""

    def file_response(self, full_path, *args, **kwargs):  # type: ignore[no-untyped-def]
        r = super().file_response(full_path, *args, **kwargs)
        durabil = "vendor" in Path(str(full_path)).parts and str(full_path).endswith(".min.js")
        r.headers["Cache-Control"] = "public, max-age=31536000, immutable" if durabil else "no-cache"
        return r


def inregistreaza(app: FastAPI) -> None:
    app.mount("/static", StaticCuRevalidare(directory=str(STATIC)), name="static")
    app.include_router(router)
    app.include_router(router_operare)
    app.include_router(router_motor)
    app.include_router(router_productie)
    app.include_router(router_alerte)
    app.include_router(router_aprobari)


__all__ = ["STATIC", "inregistreaza"]
