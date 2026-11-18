"""Pagina publică de programare (F12.5): sloturile libere, rezervarea (CSRF dublu-trimis, câmp-capcană, timp
minim, ca formularul de audit), întrebările de calificare opționale și anularea din linkul primit pe email.
Gândită întâi pentru telefon: o coloană, butoane mari, fără JavaScript."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from app.conturi import csrf_prelogin, jeton_csrf_prelogin, seteaza_csrf_prelogin
from app.crm import CrmRefuzat, calificare, programari
from app.db import sesiune_agentie
from app.site import audit
from app.site.web import randeaza

router = APIRouter(prefix="/site/programare", tags=["site"])


def _formular(request: Request, *, status: int = 200, **extra: object) -> HTMLResponse:
    with sesiune_agentie() as db:
        libere = programari.sloturi(db)
    zile: dict[str, list[tuple[str, str]]] = {}
    for s in libere:
        zi, _, ora = programari.eticheta(s).rpartition(", ora ")
        zile.setdefault(zi, []).append((s.isoformat(), ora))
    jeton = jeton_csrf_prelogin(request)
    r = randeaza(
        request, "site/programare.html", "programare", status=status, csrf_token=jeton,
        t=audit.jeton_formular(), zile=zile, intrebari=calificare.INTREBARI,
        introducere=calificare.INTRODUCERE, **extra,
    )  # fmt: skip
    seteaza_csrf_prelogin(r, jeton)
    return r


@router.get("")
def formular(request: Request) -> HTMLResponse:
    return _formular(request)


@router.post("", dependencies=[Depends(csrf_prelogin)])
async def rezerva(
    request: Request,
    slot: Annotated[str, Form(max_length=40)] = "",
    email: Annotated[str, Form(max_length=254)] = "",
    firma: Annotated[str, Form(max_length=200)] = "",
    nume: Annotated[str, Form(max_length=200)] = "",
    telefon: Annotated[str, Form(max_length=40)] = "",
    site_web2: Annotated[str, Form()] = "",  # câmpul-capcană
    t: Annotated[str, Form(max_length=120)] = "",
) -> Response:
    form = await request.form()
    raspunsuri = {k: str(form.get(k, "")) for k in calificare.INTREBARI}
    valori = {"email": email, "firma": firma, "nume": nume, "telefon": telefon, **raspunsuri}
    if site_web2 or not audit.verifica_jeton_formular(t):
        return _formular(request, status=422, eroare="Reîncarcă pagina și încearcă din nou.", valori=valori)
    try:
        inceput = dt.datetime.fromisoformat(slot)
        if inceput.tzinfo is None:
            raise ValueError
    except ValueError:
        return _formular(request, status=422, eroare="Alege un interval.", valori=valori)
    try:
        with sesiune_agentie() as db:
            p, _ = programari.rezerva(
                db, inceput=inceput, email=email, firma=firma, nume=nume, telefon=telefon,
                raspunsuri=raspunsuri if any(raspunsuri.values()) else None,
            )  # fmt: skip
            cand = programari.eticheta(p.inceput)
    except CrmRefuzat as exc:
        return _formular(request, status=422, eroare=str(exc), valori=valori)
    return randeaza(
        request, "site/audit_mesaj.html", "programare", titlu="Apel programat",
        mesaj=f"Te sunăm {cand} (ora României). Ți-am trimis pe email invitația de calendar.",
    )  # fmt: skip


@router.get("/anulare/{jeton}")
def pagina_anulare(request: Request, jeton: str) -> HTMLResponse:
    with sesiune_agentie() as db:
        p = programari.dupa_jeton(db, jeton)
        if p is None:
            raise HTTPException(status_code=404, detail="Linkul nu este valid.")
        cand, stare = programari.eticheta(p.inceput), p.stare
    csrf = jeton_csrf_prelogin(request)
    r = randeaza(
        request,
        "site/programare_anulare.html",
        "programare",
        jeton=jeton,
        cand=cand,
        stare=stare,
        csrf_token=csrf,
    )
    seteaza_csrf_prelogin(r, csrf)
    return r


@router.post("/anulare/{jeton}", dependencies=[Depends(csrf_prelogin)])
def anuleaza(request: Request, jeton: str) -> HTMLResponse:
    """Jetonul de 256 de biți din email autentifică; butonul de pe pagină poartă și CSRF dublu-trimis."""
    with sesiune_agentie() as db:
        p = programari.anuleaza(db, jeton)
        if p is None:
            raise HTTPException(status_code=404, detail="Linkul nu este valid.")
        cand = programari.eticheta(p.inceput)
    return randeaza(
        request, "site/programare_anulare.html", "programare", jeton=jeton, cand=cand, stare="anulata"
    )
