"""Modulul conturi: clienți, utilizatori, roluri, autentificare, sesiuni. Vezi docs/21 și docs/18.5."""

from fastapi import FastAPI

from app.conturi.dependente import (
    DbSession,
    NecesitaAutentificare,
    UtilizatorCurent,
    csrf_prelogin,
    csrf_protect,
    current_user,
    require_permission,
    require_role,
    tratare_neautentificat,
)
from app.conturi.roluri import Permisiune, Rol, este_agentie, poate
from app.conturi.servicii import Actor, DateInvalide, PermisiuneRefuzata, cauta_clienti, lista_clienti
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
    "cauta_clienti",
    "csrf_prelogin",
    "csrf_protect",
    "current_user",
    "este_agentie",
    "inregistreaza",
    "lista_clienti",
    "poate",
    "require_permission",
    "require_role",
    "router",
]
