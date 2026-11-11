"""Rutele conturilor: autentificare, al doilea factor, înrolare, ieșire. Interfața finală vine în F2.9."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select

from app.conturi import autentificare, criptare, sesiuni
from app.conturi.autentificare import Rezultat
from app.conturi.dependente import (
    COOKIE_CSRF,
    COOKIE_SESIUNE,
    UtilizatorCurent,
    csrf_prelogin,
    csrf_protect,
    ip_client,
    nume_cookie,
    parse_uuid,
    require_role,
    sesiune_oarecare,
    sesiune_optionala,
    seteaza_cookie,
    sterge_cookie,
)
from app.conturi.modele import Alocare, Client
from app.conturi.roluri import ROLURI_AGENTIE, Rol, are_scop_agentie
from app.conturi.sabloane import randare
from app.conturi.sesiuni import SesiuneCurenta
from app.db import ContextDb, sesiune, sesiune_auth
from app.operare import audit

router = APIRouter(prefix="/conturi", tags=["conturi"])

MESAJ_INVALID = "Adresa de email sau parola sunt incorecte."
MESAJ_BLOCAT = "Prea multe încercări. Încearcă din nou peste câteva minute."
MESAJ_COD_INVALID = "Cod incorect sau deja folosit."
ACASA = "/conturi/eu"

Oarecare = Annotated[SesiuneCurenta, Depends(sesiune_oarecare)]


def _redirect(tinta: str, jeton: str | None = None) -> RedirectResponse:
    r = RedirectResponse(tinta, status_code=303)
    if jeton:
        seteaza_cookie(r, COOKIE_SESIUNE, jeton)
    return r


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.get("/login")
def login_form(request: Request) -> Response:
    existent = request.cookies.get(nume_cookie(COOKIE_CSRF), "")
    token = existent if 20 <= len(existent) <= 100 else criptare.jeton_nou()
    r = randare(request, "conturi/login.html", csrf_token=token)
    seteaza_cookie(r, COOKIE_CSRF, token)
    return r


@router.post("/login", dependencies=[Depends(csrf_prelogin)])
def login(
    request: Request,
    email: Annotated[str, Form(max_length=254)],
    parola: Annotated[str, Form(max_length=1024)],
    csrf_token: Annotated[str, Form()],
    veche: Annotated[SesiuneCurenta | None, Depends(sesiune_optionala)],
) -> Response:
    with sesiune_auth() as db:
        rez = autentificare.autentifica_cu_parola(
            db,
            email=email,
            parola=parola,
            ip=ip_client(request),
            user_agent=_user_agent(request),
            sesiune_veche=veche,
        )
    if rez.rezultat is Rezultat.OK and rez.jeton:
        return _redirect(rez.urmator or ACASA, rez.jeton)
    if rez.rezultat is Rezultat.BLOCAT:
        return randare(request, "conturi/login.html", 429, csrf_token=csrf_token, eroare=MESAJ_BLOCAT)
    return randare(request, "conturi/login.html", 401, csrf_token=csrf_token, eroare=MESAJ_INVALID)


@router.get("/2fa")
def al_doilea_factor_form(request: Request, s: Oarecare) -> Response:
    if s.mfa_verificat:
        return _redirect(ACASA)
    if not s.totp_activ:
        return _redirect("/conturi/2fa/inrolare")
    return randare(request, "conturi/2fa.html", csrf_token=s.csrf_token)


@router.post("/2fa", dependencies=[Depends(csrf_protect)])
def al_doilea_factor(request: Request, s: Oarecare, cod: Annotated[str, Form(max_length=64)]) -> Response:
    if s.mfa_verificat or not s.totp_activ:
        return _redirect(ACASA)
    with sesiune_auth() as db:
        rez = autentificare.verifica_al_doilea_factor(
            db, s, cod, ip=ip_client(request), user_agent=_user_agent(request)
        )
    if rez.rezultat is Rezultat.OK and rez.jeton:
        return _redirect(ACASA, rez.jeton)
    eroare = MESAJ_BLOCAT if rez.rezultat is Rezultat.BLOCAT else MESAJ_COD_INVALID
    return randare(
        request,
        "conturi/2fa.html",
        429 if rez.rezultat is Rezultat.BLOCAT else 401,
        csrf_token=s.csrf_token,
        eroare=eroare,
    )


@router.get("/2fa/inrolare")
def inrolare_form(request: Request, s: Oarecare) -> Response:
    with sesiune_auth() as db:
        inr = autentificare.incepe_inrolare(db, s)
    if inr is None:
        return _redirect(ACASA)
    return randare(
        request, "conturi/2fa_inrolare.html", csrf_token=s.csrf_token, secret=inr.secret, uri=inr.uri
    )


@router.post("/2fa/inrolare", dependencies=[Depends(csrf_protect)])
def inrolare(request: Request, s: Oarecare, cod: Annotated[str, Form(max_length=64)]) -> Response:
    with sesiune_auth() as db:
        rez = autentificare.confirma_inrolare(
            db, s, cod, ip=ip_client(request), user_agent=_user_agent(request)
        )
        inr = None if rez.rezultat is Rezultat.OK else autentificare.incepe_inrolare(db, s)
    if rez.rezultat is Rezultat.OK and rez.jeton:
        # Codurile de recuperare se arată o singură dată, direct în acest răspuns (nu într-un redirect).
        r = randare(request, "conturi/coduri_recuperare.html", csrf_token="", coduri=rez.coduri_recuperare)
        seteaza_cookie(r, COOKIE_SESIUNE, rez.jeton)
        return r
    if inr is None:
        return _redirect(ACASA)
    eroare = MESAJ_BLOCAT if rez.rezultat is Rezultat.BLOCAT else MESAJ_COD_INVALID
    return randare(
        request,
        "conturi/2fa_inrolare.html",
        429 if rez.rezultat is Rezultat.BLOCAT else 401,
        csrf_token=s.csrf_token,
        secret=inr.secret,
        uri=inr.uri,
        eroare=eroare,
    )


@router.post("/iesire", dependencies=[Depends(csrf_protect)])
def iesire(s: Oarecare) -> Response:
    with sesiune_auth() as db:
        sesiuni.revoca(db, s.sesiune_id)
        audit.record(
            db, "autentificare.iesire", utilizator_id=s.utilizator_id, tenant_id=s.tenant_apartenenta
        )
    r = _redirect("/conturi/login")
    sterge_cookie(r, COOKIE_SESIUNE)
    return r


@router.get("/eu")
def eu(request: Request, u: UtilizatorCurent) -> Response:
    nume_client = None
    if u.tenant_id:
        with sesiune(u.context_db()) as db:
            nume_client = db.execute(select(Client.nume).where(Client.id == u.tenant_id)).scalar_one_or_none()
    return randare(request, "conturi/eu.html", csrf_token=u.csrf_token, utilizator=u, nume_client=nume_client)


@router.post("/client-activ", dependencies=[Depends(csrf_protect)])
def client_activ(
    u: Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))],
    tenant_id: Annotated[str, Form(max_length=64)],
) -> Response:
    """Utilizatorii de agenție aleg clientul de lucru: proprietarul oricare, ceilalți doar unul alocat."""
    ales = parse_uuid(tenant_id)
    if ales is None:
        raise HTTPException(status_code=422, detail="Client invalid.")
    ctx = ContextDb(user_id=u.utilizator_id, tenant_id=ales, agency=are_scop_agentie(u.rol))
    with sesiune(ctx) as db:
        exista = db.execute(select(Client.id).where(Client.id == ales)).first()
        alocat = db.execute(
            select(Alocare.id).where(Alocare.utilizator_id == u.utilizator_id, Alocare.tenant_id == ales)
        ).first()
    if exista is None or (u.rol is not Rol.PROPRIETAR and alocat is None):
        raise HTTPException(status_code=403, detail="Acces interzis.")
    with sesiune_auth() as db:
        sesiuni.seteaza_tenant_activ(db, u.sesiune_id, ales)
        audit.record(
            db,
            "client.activ_schimbat",
            utilizator_id=u.utilizator_id,
            tenant_id=ales,
            obiect_tip="client",
            obiect_id=ales,
        )
    return _redirect(ACASA)
