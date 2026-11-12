"""Ecranul Alerte (18.4, 22.5): coada de erori — listă pe cauze, detaliu, „reia” și „închide”.

Citirea cere un rol de agenție cu al doilea factor; „reia” și „închide” cer permisiunea
`alerte.gestioneaza`, CSRF, și se scriu în jurnalul de audit. Sesiunea de bază este cea a utilizatorului:
izolarea pe client (RLS) se aplică. Proprietarul vede toate intrările, inclusiv cele de sistem (fără
client); operatorul vede intrările clientului activ.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.config import get_settings
from app.conturi import (
    DbSession,
    Permisiune,
    SesiuneCurenta,
    csrf_protect,
    poate,
    require_permission,
    require_role,
)
from app.conturi.roluri import ROLURI_AGENTIE
from app.logging import get_logger
from app.operare import coada_erori, motor, semnale
from app.operare.coada_erori import ETICHETE_SEVERITATE, Stare
from app.operare.tabele import IntrareEroare
from app.panou.sabloane import pagina

log = get_logger("app.alerte")
router = APIRouter(prefix="/alerte", tags=["alerte"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
PoateGestiona = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.ALERTE_GESTIONEAZA))]

ETICHETE_STARE = {"noua": "nouă", "reluata": "reluată", "inchisa": "închisă"}
MESAJE = {
    "reluat": "Reluarea a fost cerută. Jobul continuă de la pasul eșuat; intrarea se închide singură "
    "când jobul se termină cu bine.",
    "inchis": "Intrarea a fost închisă și decizia a fost înregistrată.",
}
CLASA_SEVERITATE = {"critic": "pericol", "major": "pericol", "minor": "atentie", "informativ": ""}


def _intrare(db: DbSession, id_intrare: str) -> IntrareEroare:
    try:
        i = coada_erori.gaseste(db, uuid.UUID(id_intrare))
    except ValueError:
        i = None
    if i is None:  # inexistentă sau a altui client (RLS)
        raise HTTPException(status_code=404, detail="Intrarea nu există.")
    return i


def _randeaza_detaliu(
    request: Request,
    u: SesiuneCurenta,
    db: DbSession,
    i: IntrareEroare,
    *,
    status: int = 200,
    **extra: object,
) -> Response:
    return pagina(
        request,
        u,
        "panou/alerta.html",
        tab="alerte",
        status=status,
        intrare=i,
        inrudite=coada_erori.din_aceeasi_cauza(db, i),
        poate_gestiona=poate(u.rol, Permisiune.ALERTE_GESTIONEAZA),
        etichete_severitate=ETICHETE_SEVERITATE,
        etichete_stare=ETICHETE_STARE,
        clasa_severitate=CLASA_SEVERITATE,
        **extra,
    )


@router.get("")
def lista(request: Request, u: Agentie, db: DbSession, stare: str = "deschise") -> Response:
    toate = stare == "toate"
    intrari = coada_erori.lista(db, doar_deschise=not toate)
    s = get_settings()
    return pagina(
        request,
        u,
        "panou/alerte.html",
        tab="alerte",
        grupuri=coada_erori.grupeaza(intrari),
        toate=toate,
        total=len(intrari),
        workeri=semnale.stare_workeri(db, s.worker_timeout_sec),
        etichete_severitate=ETICHETE_SEVERITATE,
        etichete_stare=ETICHETE_STARE,
        clasa_severitate=CLASA_SEVERITATE,
    )


@router.get("/{id_intrare}")
def detaliu(request: Request, u: Agentie, db: DbSession, id_intrare: str, mesaj: str = "") -> Response:
    return _randeaza_detaliu(request, u, db, _intrare(db, id_intrare), mesaj=MESAJE.get(mesaj, ""))


@router.post("/{id_intrare}/reia", dependencies=[Depends(csrf_protect)])
def reia(
    request: Request,
    u: PoateGestiona,
    db: DbSession,
    id_intrare: str,
    de_la_pas: Annotated[str, Form(max_length=6)] = "",
) -> Response:
    """Reia jobul: din ultimul pas salvat (anulat/epuizat) sau de la pasul eșuat / ales (eșuat). Auditat."""
    i = _intrare(db, id_intrare)
    if i.stare == Stare.INCHISA.value:
        return _randeaza_detaliu(request, u, db, i, status=409, eroare="Intrarea este închisă.")
    if i.context.get("tip_sursa") == "livrabil":
        return _randeaza_detaliu(
            request,
            u,
            db,
            i,
            status=409,
            eroare="Nu este un job de reluat: un livrabil oprit la o limită îl reia un om din Producție.",
        )
    pas: int | None = None
    if de_la_pas.strip():
        if not de_la_pas.strip().isdigit():
            raise HTTPException(status_code=422, detail="Pas invalid.")
        pas = int(de_la_pas)
    try:
        continua_ca = motor.reia_job(i.workflow_id, pas)
    except motor.JobNereluabil as exc:
        return _randeaza_detaliu(request, u, db, i, status=409, eroare=str(exc))
    except Exception as exc:
        log.warning("reluare nereușită", extra={"tip_eroare": type(exc).__name__})
        return _randeaza_detaliu(
            request, u, db, i, status=503, eroare="Motorul nu a răspuns. Încearcă din nou în câteva secunde."
        )
    coada_erori.marcheaza_reluata(
        db,
        i,
        reluat_ca=None if continua_ca == i.workflow_id else continua_ca,
        utilizator_id=u.utilizator_id,
    )
    return RedirectResponse(f"/alerte/{i.id}?mesaj=reluat", status_code=303)


@router.post("/{id_intrare}/inchide", dependencies=[Depends(csrf_protect)])
def inchide(
    request: Request,
    u: PoateGestiona,
    db: DbSession,
    id_intrare: str,
    motiv: Annotated[str, Form(max_length=300)] = "",
) -> Response:
    """Închide intrarea cu un motiv (decizie înregistrată; nimic nu se șterge). Auditat."""
    i = _intrare(db, id_intrare)
    if i.stare == Stare.INCHISA.value:
        return _randeaza_detaliu(request, u, db, i, status=409, eroare="Intrarea este deja închisă.")
    if len(motiv.strip()) < 3:
        return _randeaza_detaliu(
            request, u, db, i, status=422, eroare="Scrie motivul închiderii (cel puțin 3 caractere)."
        )
    coada_erori.inchide(db, i, motiv=motiv, utilizator_id=u.utilizator_id)
    return RedirectResponse(f"/alerte/{i.id}?mesaj=inchis", status_code=303)
