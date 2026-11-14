"""Portalul (F7.6, F7.7, docs/19 §19.2): „Cont” — abonamentul, facturile și datele clientului."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response

from app import finante
from app.conturi import DbSession, Permisiune, SesiuneCurenta, csrf_protect, poate, require_role
from app.conturi.roluri import ROLURI_CLIENT, Rol
from app.finante import planuri
from app.panou.sabloane import pagina
from app.portal import date
from app.portal.web import tenant

router = APIRouter(prefix="/portal", tags=["portal"])
Client = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_CLIENT))]
ETICHETE = {
    "in_asteptare_plata": "așteaptă plata",
    "activ": "activ",
    "restant": "plată eșuată (perioadă de grație)",
    "suspendat": "suspendat",
    "anulat": "anulat",
}


@router.get("/cont")
def contul(request: Request, u: Client, db: DbSession, mesaj: str = "") -> Response:
    t = tenant(u)
    vede = poate(u.rol, Permisiune.FACTURI_VEDE)
    a = finante.abonamente.al_clientului(db, t) if vede else None
    return pagina(
        request,
        u,
        "portal/cont.html",
        tab="cont",
        abonament=a,
        etichete=ETICHETE,
        plan=planuri.PLANURI.get(a.plan) if a else None,
        facturi=finante.abonamente.facturi(db, t) if vede else [],
        vede_facturi=vede,
        mesaj=mesaj,
        titular=u.rol == Rol.CLIENT_TITULAR,
        stergere=date.cerere_deschisa(db, t),
        confirmare=date.CONFIRMARE,
    )


# --- datele clientului (F7.7)
# ---------------------------------------------------------------------------------
Titular = Annotated[SesiuneCurenta, Depends(require_role(Rol.CLIENT_TITULAR))]


@router.get("/date/export")
def export(u: Titular, db: DbSession) -> Response:
    corp = date.exporta(db, tenant(u), utilizator_id=u.utilizator_id)
    nume = f"ama-date-{dt.datetime.now(dt.UTC):%Y%m%d}.zip"
    return Response(
        corp,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{nume}"', "Cache-Control": "no-store"},
    )


@router.post("/date/sterge", dependencies=[Depends(csrf_protect)])
def sterge(
    request: Request, u: Titular, db: DbSession, confirmare: Annotated[str, Form(max_length=20)] = ""
) -> Response:
    try:
        date.cere_stergerea(db, tenant(u), utilizator_id=u.utilizator_id, confirmare=confirmare)
    except date.CerereInvalida as exc:
        return contul(request, u, db, mesaj=f"Cererea nu a fost înregistrată: {exc}.")
    return RedirectResponse("/portal/cont?mesaj=Cererea+de+ștergere+a+fost+înregistrată.", status_code=303)
