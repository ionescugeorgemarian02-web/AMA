"""Ecranul „Publicare” — canalele prin API (F9.10, docs/18 ecranul 14): starea fiecărei aprobări API,
conturile fiecărui client cu modul efectiv și motivul lui, expirarea tokenului, pauza, limitele citite, coada
programată.

Acțiuni: trece un canal pe asistat (ce era programat devine pachet asistat) sau înapoi pe automat;
reautorizează (OAuth: platforma întoarce omul la `/publicare/autorizare`). CSRF pe acțiuni; permisiunea
`livrabil.aproba`.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.config import get_settings
from app.connectors.contract import ETICHETE_STARE
from app.conturi import (
    DbSession,
    Permisiune,
    SesiuneCurenta,
    csrf_protect,
    lista_clienti,
    require_permission,
    require_role,
)
from app.conturi.roluri import ROLURI_AGENTIE
from app.operare import efecte
from app.operare.efecte import autorizare
from app.panou.sabloane import pagina
from app.publicare import canale, programare

router = APIRouter(prefix="/publicare", tags=["publicare"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
PoatePublica = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.LIVRABIL_APROBA))]
MESAJE = {
    "asistat": "Canalul a trecut pe asistat: postările programate au devenit pachete asistate.",
    "automat": "Canalul publică din nou automat, dacă aprobarea și contul o permit.",
    "autorizat": "Contul a fost autorizat.",
}


def redirect_oauth() -> str:
    return get_settings().public_url.rstrip("/") + "/publicare/autorizare"


def _pagina(
    request: Request, u: SesiuneCurenta, db: DbSession, *, status: int = 200, **extra: object
) -> Response:
    clienti = {c.id: c.nume for c in lista_clienti(db)}
    pauze = {(p.tenant_id, p.canal) for p in efecte.pauze(db)}
    randuri = [
        (c, canale.mod(db, c.tenant_id, c.canal), (c.tenant_id, c.canal) in pauze)
        for c in canale.conturi(db)
        if canale.are_api(c.canal)
    ]
    return pagina(
        request,
        u,
        "panou/publicare_canale.html",
        tab="meniu",
        status=status,
        aprobari=[(a, canale.ETICHETE_APROBARE[canale.StareAprobare(a.stare)]) for a in canale.aprobari(db)],
        randuri=randuri,
        clienti=clienti,
        programate=programare.ale_clientului(db, limita=50),
        etichete_stare=ETICHETE_STARE,
        **extra,
    )


@router.get("/canale")
def ecran(request: Request, u: Agentie, db: DbSession, mesaj: str = "") -> Response:
    return _pagina(request, u, db, mesaj=MESAJE.get(mesaj, ""))


def _cont(tenant: str, canal: str) -> tuple[uuid.UUID, str]:
    try:
        tid = uuid.UUID(tenant)
    except ValueError:
        raise HTTPException(status_code=404, detail="Nu există.") from None
    if not canale.are_api(canal):
        raise HTTPException(status_code=404, detail="Nu există.")
    return tid, canal


@router.post("/canale/{tenant}/{canal}/mod", dependencies=[Depends(csrf_protect)])
def schimba_modul(
    request: Request,
    u: PoatePublica,
    db: DbSession,
    tenant: str,
    canal: str,
    mod: Annotated[str, Form(max_length=20)] = "",
    motiv: Annotated[str, Form(max_length=200)] = "",
) -> Response:
    tid, canal = _cont(tenant, canal)
    if canale.cont(db, tid, canal) is None:
        raise HTTPException(status_code=404, detail="Nu există.")
    if mod == canale.Mod.ASISTAT.value:
        programare.treci_pe_asistat(db, tid, canal, utilizator_id=u.utilizator_id, motiv=motiv or "din panou")
    elif mod == canale.Mod.AUTOMAT.value:
        canale.alege_mod(
            db, tid, canal, canale.Mod.AUTOMAT, utilizator_id=u.utilizator_id, motiv=motiv or "din panou"
        )
    else:
        return _pagina(request, u, db, status=422, eroare="Mod necunoscut.")
    return RedirectResponse(f"/publicare/canale?mesaj={mod}", status_code=303)


@router.post("/canale/{tenant}/{canal}/autorizeaza", dependencies=[Depends(csrf_protect)])
def autorizeaza(request: Request, u: PoatePublica, db: DbSession, tenant: str, canal: str) -> Response:
    tid, canal = _cont(tenant, canal)
    try:
        url = autorizare.url_autorizare(db, tid, canal, redirect=redirect_oauth())
    except Exception as exc:
        db.rollback()
        return _pagina(request, u, db, status=422, eroare=f"Autorizarea nu poate porni: {exc}")
    return RedirectResponse(url, status_code=303)


@router.get("/autorizare")
def intoarcere(
    request: Request, u: PoatePublica, db: DbSession, code: str = "", state: str = "", error: str = ""
) -> Response:
    """Platforma întoarce omul aici cu codul; starea poartă clientul și canalul (verificate prin HMAC)."""
    parti = state.split(".")
    if error or not code or len(parti) != 3:
        return _pagina(request, u, db, status=422, eroare="Autorizarea a fost refuzată sau anulată.")
    canal, tenant = parti[0], parti[1]
    tid, canal = _cont(tenant, canal)
    try:
        autorizare.finalizeaza(
            db, tid, canal, cod=code, stare=state, redirect=redirect_oauth(), utilizator_id=u.utilizator_id
        )
    except Exception as exc:
        db.rollback()
        return _pagina(request, u, db, status=422, eroare=f"Autorizarea nu s-a încheiat: {exc}")
    return RedirectResponse("/publicare/canale?mesaj=autorizat", status_code=303)
