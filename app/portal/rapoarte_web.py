"""Portalul (F7.8, docs/19 §19.2 „Rapoarte”): raportul lunar, o pagină."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app import analiza
from app.conturi import DbSession, Permisiune, SesiuneCurenta, require_permission
from app.panou.sabloane import pagina
from app.portal.web import tenant

router = APIRouter(prefix="/portal", tags=["portal"])
Citeste = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.RAPOARTE_CITESTE))]


@router.get("/rapoarte")
def rapoarte(request: Request, u: Citeste, db: DbSession) -> Response:
    return pagina(
        request,
        u,
        "portal/rapoarte.html",
        tab="cont",
        rapoarte=analiza.raport_lunar.ale_clientului(db, tenant(u)),
    )
