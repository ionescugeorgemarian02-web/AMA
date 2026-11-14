"""Modulul conturi: clienți, utilizatori, roluri, autentificare, sesiuni. Vezi docs/21 și docs/18.5."""

from fastapi import FastAPI

from app.conturi.dependente import (
    DbSession,
    NecesitaAutentificare,
    UtilizatorCurent,
    csrf_prelogin,
    csrf_protect,
    current_user,
    jeton_csrf_prelogin,
    require_permission,
    require_role,
    seteaza_csrf_prelogin,
    tratare_neautentificat,
)
from app.conturi.roluri import Permisiune, Rol, este_agentie, poate
from app.conturi.servicii import (
    Actor,
    DateInvalide,
    PermisiuneRefuzata,
    are_aprobator_client,
    cauta_clienti,
    creeaza_client,
    creeaza_utilizator,
    lista_clienti,
)
from app.conturi.sesiuni import SesiuneCurenta
from app.conturi.web import router


def inregistreaza(app: FastAPI) -> None:
    """Rutele conturilor și tratarea sesiunii lipsă."""
    app.add_exception_handler(NecesitaAutentificare, tratare_neautentificat)
    app.include_router(router)


__all__ = [
    "Actor",
    "DateInvalide",
    "DbSession",
    "Permisiune",
    "PermisiuneRefuzata",
    "Rol",
    "SesiuneCurenta",
    "UtilizatorCurent",
    "are_aprobator_client",
    "cauta_clienti",
    "creeaza_client",
    "creeaza_utilizator",
    "csrf_prelogin",
    "csrf_protect",
    "current_user",
    "este_agentie",
    "inregistreaza",
    "jeton_csrf_prelogin",
    "lista_clienti",
    "poate",
    "require_permission",
    "require_role",
    "router",
    "seteaza_csrf_prelogin",
]
