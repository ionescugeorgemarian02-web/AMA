"""Rutele înscrierii (F7.6): formularul cu planul (CSRF dublu-trimis, câmp-capcană) și pagina de plată, care
trimite clientul pe pagina procesatorului (platforma nu vede date de card)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import finante
from app.conturi import DateInvalide, csrf_prelogin, jeton_csrf_prelogin, seteaza_csrf_prelogin
from app.db import sesiune_agentie
from app.finante import planuri
from app.site import audit, inscriere
from app.site.web import randeaza

router = APIRouter(prefix="/site/inscriere", tags=["site"])


def _formular(
    request: Request, *, plan: str, jeton_raport: str = "", status: int = 200, **extra: object
) -> HTMLResponse:
    firma = email = ""
    if jeton_raport:
        with sesiune_agentie() as db:
            rez = audit.raport(db, jeton_raport)
            if rez is not None:
                firma, email = rez[0].firma, rez[0].email
    j = jeton_csrf_prelogin(request)
    r = randeaza(
        request,
        "site/inscriere.html",
        "preturi",
        status=status,
        csrf_token=j,
        planuri=planuri.PLANURI,
        plan_ales=plan if plan in planuri.PLANURI else "start",
        firma=firma,
        email=email,
        jeton_raport=jeton_raport,
        t=audit.jeton_formular(),
        **extra,
    )
    seteaza_csrf_prelogin(r, j)
    return r


@router.get("")
def formular(request: Request, plan: str = "start", raport: str = "") -> HTMLResponse:
    return _formular(request, plan=plan, jeton_raport=raport)


@router.post("", dependencies=[Depends(csrf_prelogin)])
def trimite(
    request: Request,
    firma: Annotated[str, Form(max_length=200)] = "",
    email: Annotated[str, Form(max_length=254)] = "",
    plan: Annotated[str, Form(max_length=20)] = "start",
    raport: Annotated[str, Form(max_length=100)] = "",
    acord: Annotated[str, Form()] = "",
    site_web2: Annotated[str, Form()] = "",
    t: Annotated[str, Form(max_length=120)] = "",
) -> Response:
    if site_web2 or not audit.verifica_jeton_formular(t):
        raise HTTPException(status_code=400, detail="Cerere respinsă.")
    if acord != "da":
        return _formular(
            request,
            plan=plan,
            jeton_raport=raport,
            status=422,
            eroare="Bifează acordul cu termenii și acordul de prelucrare.",
        )
    try:
        with sesiune_agentie() as db:
            lead_id = None
            if raport:
                rez = audit.raport(db, raport)
                lead_id = rez[0].id if rez else None
            _, jeton = inscriere.inscrie(db, firma=firma, email=email, plan=plan, lead_id=lead_id)
    except DateInvalide as exc:
        return _formular(request, plan=plan, jeton_raport=raport, status=422, eroare=str(exc))
    return RedirectResponse(f"/site/inscriere/plata/{jeton}", status_code=303)


@router.get("/plata/{jeton}")
def plata(request: Request, jeton: str) -> HTMLResponse:
    with sesiune_agentie() as db:
        a = finante.abonamente.dupa_jeton(db, jeton)
        if a is None:
            raise HTTPException(status_code=404, detail="Nu există.")
        link = finante.abonamente.link_plata(db, a)
        stare, plan, suma = a.stare, planuri.PLANURI[a.plan].nume, a.suma
    r = randeaza(
        request, "site/plata.html", "preturi", robots="noindex", link=link, stare=stare, plan=plan, suma=suma
    )
    r.headers["Cache-Control"] = "no-store"
    return r
