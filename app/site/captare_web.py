"""Paginile de captare găzduite de platformă (F7.9): `/site/p/<slug>`, doar cele publicate de un om, cu UN
buton."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import oferta
from app.db import sesiune_agentie
from app.site.web import randeaza

router = APIRouter(prefix="/site/p", tags=["site"])


@router.get("/{slug}")
def pagina(request: Request, slug: str) -> HTMLResponse:
    with sesiune_agentie() as db:
        pg = oferta.pagini.publicata(db, slug)
        if pg is None:
            raise HTTPException(status_code=404, detail="Pagina nu există.")
        c, tinta = dict(pg.continut), pg.tinta
    return randeaza(request, "site/captare.html", f"p/{slug}", c=c, tinta=tinta)
