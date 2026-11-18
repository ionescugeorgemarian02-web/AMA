"""Pagina asistentului de suport din portal (F12.10): întrebarea, răspunsul din datele contului, istoricul."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response

from app.conturi import DbSession, SesiuneCurenta, csrf_protect, require_role
from app.conturi.roluri import ROLURI_CLIENT
from app.panou.sabloane import pagina
from app.portal import suport
from app.portal.web import tenant

router = APIRouter(prefix="/portal", tags=["portal"])
Client = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_CLIENT))]


def _pagina(
    request: Request, u: SesiuneCurenta, db: DbSession, *, status: int = 200, **extra: object
) -> Response:
    return pagina(
        request,
        u,
        "portal/suport.html",
        tab="cont",
        status=status,
        prezentare=suport.PREZENTARE,
        istoric=suport.istoric(db, tenant(u)),
        **extra,
    )


@router.get("/suport")
def formular(request: Request, u: Client, db: DbSession) -> Response:
    return _pagina(request, u, db)


@router.post("/suport", dependencies=[Depends(csrf_protect)])
def intreaba(
    request: Request, u: Client, db: DbSession, intrebare: Annotated[str, Form(max_length=1000)] = ""
) -> Response:
    try:
        r = suport.intreaba(db, tenant(u), intrebare, utilizator_id=u.utilizator_id)
    except suport.IntrebareInvalida as exc:
        return _pagina(request, u, db, status=422, eroare=str(exc))
    return _pagina(request, u, db, raspuns=r)
