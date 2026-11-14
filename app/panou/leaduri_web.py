"""Ecranul „Leaduri din site” (F7.2): cererile de audit, starea opt-in-ului și a raportului. Doar agenția
(datele
leadurilor sunt ale agenției; RLS pe contextul de agenție). CRM-ul complet vine în F12."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app import site
from app.conturi import DbSession, SesiuneCurenta, require_role
from app.conturi.roluri import ROLURI_AGENTIE
from app.panou.sabloane import pagina

router = APIRouter(prefix="/leaduri", tags=["leaduri"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
ETICHETE = {
    "neconfirmat": "neconfirmat",
    "confirmat": "confirmat",
    "audit_gata": "raport trimis",
    "client": "client",
    "retras": "retras",
}


@router.get("")
def lista(request: Request, u: Agentie, db: DbSession) -> Response:
    return pagina(
        request, u, "panou/leaduri.html", tab="meniu", leaduri=site.audit.leaduri(db), etichete=ETICHETE
    )
