"""Portalul clientului (F7.3+, docs/19 §19.2): activarea contului, Acasă cu bara de progres, interviul.

Rutele cu sesiune cer un rol de client; baza aplică RLS pe clientul utilizatorului (nu poate vedea alt
client).
Întâi pentru telefon. CSRF pe orice schimbare; auditul îl scriu serviciile."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import onboarding
from app.conturi import (
    DateInvalide,
    DbSession,
    Permisiune,
    SesiuneCurenta,
    csrf_prelogin,
    csrf_protect,
    jeton_csrf_prelogin,
    require_permission,
    require_role,
    seteaza_csrf_prelogin,
)
from app.conturi.roluri import ROLURI_CLIENT
from app.conturi.sabloane import randare
from app.db import sesiune_agentie
from app.onboarding import interviu, sesiuni
from app.panou.sabloane import pagina
from app.portal import cont, progres

router = APIRouter(prefix="/portal", tags=["portal"])
Client = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_CLIENT))]
PoateCompleta = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.ONBOARDING_COMPLETEAZA))]
MESAJE = {
    "pornit": "Interviul a pornit. Răspunde la prima întrebare.",
    "raspuns": "Răspunsul a fost salvat.",
    "compune": "Mulțumim! Pregătim profilul firmei din răspunsuri; îl vei vedea la „Creier”.",
}


def tenant(u: SesiuneCurenta) -> uuid.UUID:
    if u.tenant_id is None:
        raise HTTPException(status_code=403, detail="Acces interzis.")
    return u.tenant_id


def randeaza(
    request: Request, u: SesiuneCurenta, sablon: str, *, tab: str, status: int = 200, **ctx: object
) -> Response:
    return pagina(request, u, sablon, tab=tab, status=status, **ctx)


# --- activarea contului (fără sesiune) ---------------------------------------------------------------------


@router.get("/activare/{jeton}")
def activare(request: Request, jeton: str) -> Response:
    with sesiune_agentie() as db:
        inv = cont.dupa_jeton(db, jeton)
        email = inv.email if inv else None
    if email is None:
        return randare(request, "portal/activare.html", status=404, invalid=True)
    j = jeton_csrf_prelogin(request)
    r = randare(request, "portal/activare.html", csrf_token=j, email=email, jeton=jeton)
    seteaza_csrf_prelogin(r, j)
    return r


@router.post("/activare/{jeton}", dependencies=[Depends(csrf_prelogin)])
def activeaza(
    request: Request,
    jeton: str,
    parola: Annotated[str, Form(max_length=200)],
    nume_afisat: Annotated[str, Form(max_length=100)] = "",
) -> Response:
    try:
        cont.activeaza(jeton, parola=parola, nume_afisat=nume_afisat.strip())
    except cont.InvitatieInvalida as exc:
        return randare(request, "portal/activare.html", status=404, invalid=True, eroare=str(exc))
    except DateInvalide as exc:
        j = jeton_csrf_prelogin(request)
        with sesiune_agentie() as db:
            inv = cont.dupa_jeton(db, jeton)
        r = randare(
            request,
            "portal/activare.html",
            status=422,
            csrf_token=j,
            email=inv.email if inv else "",
            jeton=jeton,
            eroare=str(exc),
        )
        seteaza_csrf_prelogin(r, j)
        return r
    return RedirectResponse("/conturi/login?activat=1", status_code=303)


# --- Acasă ---------------------------------------------------------------------------------------------


@router.get("")
def acasa(request: Request, u: Client, db: DbSession) -> Response:
    lista = progres.pasi(db, tenant(u))
    return randeaza(request, u, "portal/acasa.html", tab="acasa", pasi=lista, procent=progres.procent(lista))


# --- interviul (docs/19 §19.3, pașii 2–3; aceleași funcții ca ecranul din panou)
# ------------------------------


@router.get("/onboarding")
def interviul(
    request: Request, u: Client, db: DbSession, mesaj: str = "", status: int = 200, eroare: str = ""
) -> Response:
    t = tenant(u)
    s = sesiuni.sesiune_deschisa(db, t)
    date: dict[str, object] = {"s": s}
    if s is not None:
        urm = sesiuni.urmatoarea(db, s.id)
        date.update(progres=sesiuni.progres(db, s.id), urmatoarea=urm)
        if urm is not None:
            date.update(
                sectiune=interviu.sectiune_intrebare(urm.cod).titlu,
                ajutor=interviu.camp_intrebare(urm.cod).ajutor,
            )
    return randeaza(
        request,
        u,
        "portal/onboarding.html",
        tab="onboarding",
        status=status,
        mesaj=MESAJE.get(mesaj, ""),
        eroare=eroare,
        **date,
    )


@router.post("/onboarding/porneste", dependencies=[Depends(csrf_protect)])
def porneste(u: PoateCompleta, db: DbSession) -> Response:
    sesiuni.deschide(db, tenant_id=tenant(u), utilizator_id=u.utilizator_id)
    return RedirectResponse("/portal/onboarding?mesaj=pornit", status_code=303)


@router.post("/onboarding/raspunde", dependencies=[Depends(csrf_protect)])
def raspunde(
    request: Request,
    u: PoateCompleta,
    db: DbSession,
    intrebare_id: Annotated[str, Form()],
    raspuns: Annotated[str, Form(max_length=6000)],
) -> Response:
    s = sesiuni.sesiune_deschisa(db, tenant(u))
    if s is None:
        raise HTTPException(status_code=404, detail="Nu există un interviu deschis.")
    try:
        qid = uuid.UUID(intrebare_id)
        sesiuni.raspunde(db, s.id, qid, raspuns, utilizator_id=u.utilizator_id)
    except (ValueError, onboarding.EroareOnboarding) as exc:
        db.rollback()
        return interviul(request, u, db, status=422, eroare=str(exc))
    return RedirectResponse("/portal/onboarding?mesaj=raspuns", status_code=303)


@router.post("/onboarding/compune", dependencies=[Depends(csrf_protect)])
def compune(u: PoateCompleta, db: DbSession) -> Response:
    t = tenant(u)
    s = sesiuni.sesiune_deschisa(db, t)
    if s is None or not sesiuni.progres(db, s.id).terminat:
        raise HTTPException(status_code=409, detail="Interviul nu este terminat.")
    onboarding.fluxuri.trimite_compunerea(t, s.id, u.utilizator_id, cheie=f"brief:{s.id}")
    return RedirectResponse("/portal?mesaj=compune", status_code=303)
