"""Rutele auditului gratuit (F7.2): formularul (CSRF dublu-trimis, câmp-capcană, timp minim), confirmarea
din email (opt-in dublu) și raportul. Răspunsul la trimitere e același pentru orice adresă."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from app.conturi import csrf_prelogin, jeton_csrf_prelogin, seteaza_csrf_prelogin
from app.db import sesiune_agentie
from app.site import audit
from app.site.web import randeaza

router = APIRouter(prefix="/site/audit", tags=["site"])


def _formular(request: Request, *, status: int = 200, **extra: object) -> HTMLResponse:
    jeton = jeton_csrf_prelogin(request)
    r = randeaza(
        request,
        "site/audit.html",
        "audit",
        status=status,
        csrf_token=jeton,
        t=audit.jeton_formular(),
        **extra,
    )
    seteaza_csrf_prelogin(r, jeton)
    return r


@router.get("")
def formular(request: Request) -> HTMLResponse:
    return _formular(request)


@router.post("", dependencies=[Depends(csrf_prelogin)])
def trimite(
    request: Request,
    email: Annotated[str, Form(max_length=254)] = "",
    firma: Annotated[str, Form(max_length=200)] = "",
    site_url: Annotated[str, Form(max_length=300)] = "",
    acord: Annotated[str, Form()] = "",
    site_web2: Annotated[str, Form()] = "",  # câmpul-capcană (ascuns oamenilor)
    t: Annotated[str, Form(max_length=120)] = "",
) -> Response:
    try:
        with sesiune_agentie() as db:
            audit.cere(
                db,
                email=email,
                firma=firma,
                site_url=site_url,
                acord=acord == "da",
                capcana=site_web2,
                jeton=t,
            )
    except audit.CerereInvalida as exc:
        return _formular(
            request,
            status=422,
            eroare=str(exc),
            valori={"email": email, "firma": firma, "site_url": site_url},
        )
    return randeaza(
        request,
        "site/audit_mesaj.html",
        "audit",
        titlu="Verifică-ți emailul",
        mesaj="Ți-am trimis un email. Confirmă adresa din linkul primit și pornim auditul.",
    )


@router.get("/confirma/{jeton}")
def confirma(request: Request, jeton: str) -> HTMLResponse:
    with sesiune_agentie() as db:
        lead = audit.confirma(db, jeton)
    if lead is None:
        raise HTTPException(status_code=404, detail="Linkul nu este valid sau a expirat.")
    return randeaza(
        request,
        "site/audit_mesaj.html",
        "audit",
        titlu="Adresa este confirmată",
        mesaj="Auditul a pornit. Raportul îți ajunge pe email în câteva minute.",
    )


@router.get("/raport/{jeton}")
def raport(request: Request, jeton: str) -> HTMLResponse:
    with sesiune_agentie() as db:
        rez = audit.raport(db, jeton)
        if rez is None:
            raise HTTPException(status_code=404, detail="Raportul nu există.")
        lead, a = rez
        firma, site_url, rap = lead.firma, lead.site_url, a.raport
    r = randeaza(
        request,
        "site/audit_raport.html",
        "audit",
        robots="noindex",
        jeton=jeton,
        firma=firma,
        site_url=site_url,
        raport=rap,
    )
    r.headers["Cache-Control"] = "no-store"
    return r
