"""Ecranul Materiale (F-editorial): activele cu rol vizual incert, de clasificat, și cererile de material
lipsă.

Operatorul alege clientul, vede fotografiile și filmările fără rol (`active.rol_vizual` NULL) și le dă rolul
și subiectul (ce se vede), cu urmă în audit (`media.biblioteca.clasifica`). Tot aici apar cererile precise ale
storyboardului („Încarcă o fotografie verticală cu …”); după încărcare, „Reia livrabilul” pornește din nou
producția video a aceluiași livrabil. Acțiunile cer `livrabil.editeaza` și CSRF.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import media
from app.conturi import (
    DbSession,
    Permisiune,
    SesiuneCurenta,
    csrf_protect,
    lista_clienti,
    require_permission,
    require_role,
)
from app.conturi.roluri import ROLURI_AGENTIE, poate
from app.panou.sabloane import pagina

router = APIRouter(prefix="/materiale", tags=["materiale"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
PoateEdita = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.LIVRABIL_EDITEAZA))]
MESAJE = {"clasificat": "Activul a fost clasificat.", "reluat": "Livrabilul a fost repus în producție."}
ETICHETE_ROL = {
    "fotografie": "fotografie",
    "filmare": "filmare",
    "ilustratie": "ilustrație",
    "logo": "siglă",
    "coperta": "copertă",
    "export": "export",
}


def _uuid(text: str, ce: str) -> uuid.UUID:
    try:
        return uuid.UUID(text)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"{ce} necunoscut.") from None


def _ecran(
    request: Request,
    u: SesiuneCurenta,
    db: DbSession,
    tenant_id: uuid.UUID | None,
    *,
    status: int = 200,
    **extra: Any,
) -> Response:
    clienti = {c.id: c.nume for c in lista_clienti(db)}
    if tenant_id is not None and tenant_id not in clienti:
        raise HTTPException(status_code=404, detail="Client necunoscut.")
    return pagina(
        request,
        u,
        "panou/materiale.html",
        tab="meniu",
        status=status,
        clienti=clienti,
        client=tenant_id,
        neclasificate=media.biblioteca.neclasificate(db, tenant_id) if tenant_id else [],
        cereri=media.cereri.deschise(db, tenant_id) if tenant_id else [],
        roluri=ETICHETE_ROL,
        poate_edita=poate(u.rol, Permisiune.LIVRABIL_EDITEAZA),
        **extra,
    )


@router.get("")
def ecran_materiale(
    request: Request, u: Agentie, db: DbSession, client: str = "", mesaj: str = ""
) -> Response:
    return _ecran(request, u, db, _uuid(client, "Client") if client else None, mesaj=MESAJE.get(mesaj, ""))


@router.post("/{client}/active/{activ}/clasifica", dependencies=[Depends(csrf_protect)])
async def clasifica(
    request: Request, client: str, activ: str, u: Agentie, _p: PoateEdita, db: DbSession
) -> Response:
    tid, aid = _uuid(client, "Client"), _uuid(activ, "Activ")
    f = await request.form()
    rol = str(f.get("rol") or "") or None
    a = media.biblioteca.citeste_activ(db, aid)
    if a is None or a.tenant_id != tid:
        raise HTTPException(status_code=404, detail="Activ necunoscut.")
    try:
        media.biblioteca.clasifica(db, aid, rol, str(f.get("subiect") or ""), utilizator_id=u.utilizator_id)
    except ValueError as exc:
        return _ecran(request, u, db, tid, status=422, eroare=str(exc))
    return RedirectResponse(f"/materiale?client={tid}&mesaj=clasificat", status_code=303)


@router.post("/{client}/livrabile/{livrabil}/reia", dependencies=[Depends(csrf_protect)])
def reia(client: str, livrabil: str, u: Agentie, _p: PoateEdita, db: DbSession) -> Response:
    tid, lid = _uuid(client, "Client"), _uuid(livrabil, "Livrabil")
    if not media.cereri.deschise(db, tid, lid):
        raise HTTPException(status_code=404, detail="Livrabilul nu așteaptă material.")
    media.fluxuri.reia_livrabil(db, tid, lid, utilizator_id=u.utilizator_id)
    return RedirectResponse(f"/materiale?client={tid}&mesaj=reluat", status_code=303)
