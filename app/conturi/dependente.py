"""Dependențe FastAPI: `current_user`, `require_role`, `require_permission`, `db_session`, `csrf_protect`."""

import uuid
from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.conturi import criptare, sesiuni
from app.conturi.modele import Alocare
from app.conturi.roluri import Permisiune, Rol, are_scop_agentie, este_agentie, poate
from app.conturi.sesiuni import SesiuneCurenta
from app.db import ContextDb, sesiune, sesiune_auth

COOKIE_SESIUNE = "ama_sesiune"
COOKIE_CSRF = "ama_csrf"
METODE_SIGURE = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
PAGINA_LOGIN = "/conturi/login"


class NecesitaAutentificare(Exception):
    def __init__(self, tinta: str = PAGINA_LOGIN) -> None:
        super().__init__(tinta)
        self.tinta = tinta


def nume_cookie(baza: str) -> str:
    """În afara dev/test cookie-urile sunt `Secure` și cu prefix `__Host-` (fără Domain, Path=/)."""
    return f"__Host-{baza}" if get_settings().cookie_secure else baza


def seteaza_cookie(response: Response, baza: str, valoare: str) -> None:
    response.set_cookie(
        nume_cookie(baza),
        valoare,
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
        path="/",
    )


def sterge_cookie(response: Response, baza: str) -> None:
    response.delete_cookie(
        nume_cookie(baza), path="/", httponly=True, samesite="lax", secure=get_settings().cookie_secure
    )


def ip_client(request: Request) -> str:
    """Adresa peer-ului. În spatele proxy-ului, serverul rulează cu `--proxy-headers`."""
    return request.client.host if request.client else "necunoscut"


def tratare_neautentificat(request: Request, exc: Exception) -> Response:
    tinta = exc.tinta if isinstance(exc, NecesitaAutentificare) else PAGINA_LOGIN
    if request.headers.get("hx-request"):
        return Response(status_code=401, headers={"HX-Redirect": tinta})
    return RedirectResponse(tinta, status_code=303)


def sesiune_optionala(request: Request) -> SesiuneCurenta | None:
    jeton = request.cookies.get(nume_cookie(COOKIE_SESIUNE))
    if not jeton:
        return None
    with sesiune_auth() as db:
        return sesiuni.incarca(db, jeton)


def sesiune_oarecare(s: Annotated[SesiuneCurenta | None, Depends(sesiune_optionala)]) -> SesiuneCurenta:
    """Sesiune validă, chiar și în așteptarea celui de-al doilea factor (pentru paginile 2FA)."""
    if s is None:
        raise NecesitaAutentificare()
    return s


def current_user(s: Annotated[SesiuneCurenta, Depends(sesiune_oarecare)]) -> SesiuneCurenta:
    """Utilizatorul autentificat complet. Cu al doilea factor lipsă, trimite la pasul care lipsește."""
    if not s.mfa_verificat:
        raise NecesitaAutentificare("/conturi/2fa" if s.totp_activ else "/conturi/2fa/inrolare")
    return s


def require_role(*roluri: Rol) -> Callable[[SesiuneCurenta], SesiuneCurenta]:
    permise = frozenset(roluri)

    def verifica(u: Annotated[SesiuneCurenta, Depends(current_user)]) -> SesiuneCurenta:
        if u.rol not in permise:
            raise HTTPException(status_code=403, detail="Acces interzis.")
        return u

    return verifica


def require_permission(permisiune: Permisiune) -> Callable[[SesiuneCurenta], SesiuneCurenta]:
    def verifica(u: Annotated[SesiuneCurenta, Depends(current_user)]) -> SesiuneCurenta:
        if not poate(u.rol, permisiune):
            raise HTTPException(status_code=403, detail="Acces interzis.")
        return u

    return verifica


def context_verificat(u: SesiuneCurenta) -> ContextDb:
    """Contextul bazei pentru utilizator. Un utilizator de agenție fără scop general lucrează doar într-un
    client alocat lui; dacă alocarea a dispărut între timp, clientul activ se ignoră (refuz implicit)."""
    ctx = u.context_db()
    if este_agentie(u.rol) and not are_scop_agentie(u.rol) and u.tenant_activ_id is not None:
        with sesiune(ContextDb(user_id=u.utilizator_id, tenant_id=u.tenant_activ_id)) as db:
            alocat = db.execute(
                select(Alocare.id).where(
                    Alocare.utilizator_id == u.utilizator_id, Alocare.tenant_id == u.tenant_activ_id
                )
            ).first()
        if alocat is None:
            return ContextDb(user_id=u.utilizator_id)
    return ctx


def db_session(u: Annotated[SesiuneCurenta, Depends(current_user)]) -> Iterator[Session]:
    """Sesiune de bază cu clientul curent aplicat (RLS). Commit la final, rollback la excepție.
    Se declară cu `DbSession`, ca să se încheie înainte de trimiterea răspunsului."""
    with sesiune(context_verificat(u)) as db:
        yield db


DbSession = Annotated[Session, Depends(db_session, scope="function")]
UtilizatorCurent = Annotated[SesiuneCurenta, Depends(current_user)]


def _jeton_cerere(request: Request) -> str | None:
    return request.headers.get("x-csrf-token")


async def _jeton_formular(request: Request) -> str | None:
    val = (await request.form()).get("csrf_token")
    return val if isinstance(val, str) else None


async def csrf_protect(
    request: Request, s: Annotated[SesiuneCurenta | None, Depends(sesiune_optionala)]
) -> None:
    """CSRF pe cereri care schimbă starea: jeton per sesiune, în `X-CSRF-Token` sau în câmpul `csrf_token`."""
    if request.method in METODE_SIGURE:
        return
    primit = _jeton_cerere(request) or await _jeton_formular(request)
    if s is None or not primit or not criptare.egale(primit, s.csrf_token):
        raise HTTPException(status_code=403, detail="Cerere respinsă (jeton CSRF lipsă sau greșit).")


async def csrf_prelogin(request: Request) -> None:
    """Înainte de sesiune: jeton dublu-trimis (cookie + câmp de formular)."""
    cookie = request.cookies.get(nume_cookie(COOKIE_CSRF))
    primit = _jeton_cerere(request) or await _jeton_formular(request)
    if not cookie or not primit or not criptare.egale(primit, cookie):
        raise HTTPException(status_code=403, detail="Cerere respinsă (jeton CSRF lipsă sau greșit).")


def parse_uuid(valoare: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(valoare)
    except ValueError:
        return None
