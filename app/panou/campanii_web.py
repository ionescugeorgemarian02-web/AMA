"""Ecranul „Campanii” (F4.11, docs/18 §18.2, ecranul 7): strategiile pe client — lista, detaliul și decizia
(aprobă / respinge cu motiv). Minim, întâi pentru telefon. Revizuirile, arborele de indicatori,
experimentele și pivotul sunt F13.6.

CSRF pe orice schimbare, permisiunea `creier.editeaza` pentru aprobare / respingere (audit scris de
serviciul Creierului) și
`onboarding.completeaza` pentru a cere o propunere nouă. Aprobarea trece prin poarta compartimentului:
o strategie cu un
element lipsă nu poate fi aprobată.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import creier, onboarding
from app.conturi import (
    DbSession,
    Permisiune,
    SesiuneCurenta,
    csrf_protect,
    lista_clienti,
    poate,
    require_permission,
    require_role,
)
from app.conturi.roluri import ROLURI_AGENTIE
from app.onboarding import strategie
from app.panou.sabloane import pagina

router = APIRouter(prefix="/campanii", tags=["campanii"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
PoateAproba = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.CREIER_EDITEAZA))]
PoatePropune = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.ONBOARDING_COMPLETEAZA))]
MOTIV_MAXIM = 300
MESAJE = {
    "aprobata": "Strategia a fost aprobată.",
    "respinsa": "Strategia a fost respinsă, cu motivul tău.",
    "pornita": "Strategia se pregătește (modelul poate amâna). Reîncarcă pagina peste câteva secunde.",
}


def _id(valoare: str) -> uuid.UUID:
    try:
        return uuid.UUID(valoare)
    except ValueError:
        raise HTTPException(status_code=404, detail="Nu există.") from None


def _client(db: DbSession, client_id: str):  # type: ignore[no-untyped-def]
    cid = _id(client_id)
    for c in lista_clienti(db):
        if c.id == cid:
            return c
    raise HTTPException(status_code=404, detail="Clientul nu există.")


def _starea(db: DbSession, tenant_id: uuid.UUID) -> str:
    randuri = strategie.strategii(db, tenant_id)
    if not randuri:
        return "fără strategie"
    if any(v is not None for _, v in randuri):
        return "aprobată"
    return "în așteptare"


def _pagina(
    request: Request, u: SesiuneCurenta, db: DbSession, client_id: str, *, status: int = 200, **extra: object
) -> Response:
    c = _client(db, client_id)
    intrari = []
    for i, aprobata in strategie.strategii(db, c.id):
        versiuni = creier.istoric(db, i.id)
        intrari.append(
            {
                "intrare": i,
                "aprobata": aprobata,
                "in_asteptare": [v for v in versiuni if v.stare == "propus"],
                "respinse": [v for v in versiuni if v.stare == "retras" and v.retras_cauza == "respins"],
                "numar_versiuni": len(versiuni),
            }
        )
    return pagina(
        request, u, "panou/campanii.html", tab="meniu", status=status, client=c, intrari=intrari,
        poate_aproba=poate(u.rol, Permisiune.CREIER_EDITEAZA),
        poate_propune=poate(u.rol, Permisiune.ONBOARDING_COMPLETEAZA), **extra,
    )  # fmt: skip


@router.get("")
def lista(request: Request, u: Agentie, db: DbSession) -> Response:
    clienti = lista_clienti(db)
    return pagina(
        request, u, "panou/campanii_lista.html", tab="meniu", clienti=clienti,
        stari={c.id: _starea(db, c.id) for c in clienti},
    )  # fmt: skip


@router.get("/{client_id}")
def detaliu(request: Request, u: Agentie, db: DbSession, client_id: str, mesaj: str = "") -> Response:
    return _pagina(request, u, db, client_id, mesaj=MESAJE.get(mesaj, ""))


@router.post("/{client_id}/propune", dependencies=[Depends(csrf_protect)])
def propune(request: Request, u: PoatePropune, db: DbSession, client_id: str) -> Response:
    c = _client(db, client_id)
    tenant = c.id
    db.commit()
    onboarding.fluxuri.trimite_strategia(
        tenant, u.utilizator_id, cheie=f"strategie:{tenant}:{uuid.uuid4().hex[:8]}"
    )
    return RedirectResponse(f"/campanii/{tenant}?mesaj=pornita", status_code=303)


@router.post("/{client_id}/{intrare_id}/aproba", dependencies=[Depends(csrf_protect)])
def aproba(
    request: Request, u: PoateAproba, db: DbSession, client_id: str, intrare_id: str,
    versiune: Annotated[int, Form(ge=1)],
) -> Response:  # fmt: skip
    c = _client(db, client_id)
    try:
        creier.aproba(db, _id(intrare_id), versiune, utilizator_id=u.utilizator_id)
    except creier.IntrareInexistenta:
        raise HTTPException(status_code=404, detail="Strategia nu există.") from None
    except (creier.TranzitieNepermisa, creier.RegulaCreier) as exc:
        db.rollback()
        probleme = getattr(exc, "probleme", None)
        return _pagina(
            request, u, db, client_id, status=409 if not probleme else 422,
            eroare="Strategia nu poate fi aprobată: " + ("; ".join(probleme[:6]) if probleme else str(exc)),
        )  # fmt: skip
    return RedirectResponse(f"/campanii/{c.id}?mesaj=aprobata", status_code=303)


@router.post("/{client_id}/{intrare_id}/respinge", dependencies=[Depends(csrf_protect)])
def respinge(
    request: Request, u: PoateAproba, db: DbSession, client_id: str, intrare_id: str,
    versiune: Annotated[int, Form(ge=1)], motiv: Annotated[str, Form(max_length=MOTIV_MAXIM)] = "",
) -> Response:  # fmt: skip
    c = _client(db, client_id)
    if len(motiv.strip()) < 3:
        return _pagina(
            request, u, db, client_id, status=422, eroare="Scrie motivul respingerii (cel puțin 3 caractere)."
        )
    try:
        creier.retrage(
            db, _id(intrare_id), versiune, utilizator_id=u.utilizator_id, motiv=motiv.strip(),
            cauza=creier.CauzaRetragere.RESPINS,
        )  # fmt: skip
    except creier.IntrareInexistenta:
        raise HTTPException(status_code=404, detail="Strategia nu există.") from None
    except creier.TranzitieNepermisa as exc:
        db.rollback()
        return _pagina(request, u, db, client_id, status=409, eroare=str(exc))
    return RedirectResponse(f"/campanii/{c.id}?mesaj=respinsa", status_code=303)
