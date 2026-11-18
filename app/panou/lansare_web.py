"""Ecranele lansării (F15.5 pilotul, F15.6 lista de go-live), doar pentru proprietar.

- `/lansare/pilot`: clienții din pilot, cu indicatorii calculați din urme (aprobarea din prima, incidentele
  critice), feedback-ul săptămânal și starea porții; înscrierea, feedback-ul, incidentul, raportul (CSRF).
"""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select

from app import conturi
from app.conturi import DbSession, Rol, SesiuneCurenta, csrf_protect, require_role
from app.lansare import PilotRaport, pilot
from app.panou.sabloane import pagina

router = APIRouter(prefix="/lansare", tags=["lansare"])
Proprietar = Annotated[SesiuneCurenta, Depends(require_role(Rol.PROPRIETAR))]


def _id(text: str) -> uuid.UUID:
    try:
        return uuid.UUID(text)
    except ValueError:
        raise HTTPException(400, "Client invalid.") from None


def _inapoi(mesaj: str) -> RedirectResponse:
    return RedirectResponse(f"/lansare/pilot?mesaj={mesaj}", status_code=303)


@router.get("/pilot")
def ecran_pilot(
    request: Request, u: Proprietar, db: DbSession, mesaj: str = "", eroare: str = ""
) -> Response:
    azi = dt.datetime.now(dt.UTC).date()
    nume = {c.id: c.nume for c in conturi.lista_clienti(db)}
    randuri = []
    for p in pilot.clienti(db):
        rapoarte = db.execute(
            select(PilotRaport)
            .where(PilotRaport.tenant_id == p.tenant_id)
            .order_by(PilotRaport.saptamana.desc())
        ).scalars().all()  # fmt: skip
        poarta = pilot.stare_poarta(db, p, azi)
        randuri.append({"p": p, "nume": nume.get(p.tenant_id, str(p.tenant_id)), "poarta": poarta,
                        "rapoarte": [r.continut for r in rapoarte[:8]]})  # fmt: skip
    in_pilot = {p.tenant_id for p in pilot.clienti(db)}
    return pagina(
        request, u, "panou/lansare_pilot.html", tab="meniu", randuri=randuri, mesaj=mesaj, eroare=eroare,
        candidati=[(i, n) for i, n in nume.items() if i not in in_pilot], azi=azi.isoformat(),
        prag=pilot.PRAG_APROBARE,
    )  # fmt: skip


@router.post("/pilot/inscrie", dependencies=[Depends(csrf_protect)])
def inscrie(
    u: Proprietar,
    db: DbSession,
    tenant_id: Annotated[str, Form()],
    pret_lei: Annotated[int, Form(ge=0, le=100_000)],
) -> Response:
    try:
        pilot.inscrie(
            db, _id(tenant_id), pret_lunar_bani=pret_lei * 100, utilizator_id=u.utilizator_id, rol=u.rol
        )
    except pilot.PilotInvalid as exc:
        return RedirectResponse(f"/lansare/pilot?eroare={exc}", status_code=303)
    return _inapoi("inscris")


@router.post("/pilot/{tenant_id}/feedback", dependencies=[Depends(csrf_protect)])
def feedback(
    u: Proprietar,
    db: DbSession,
    tenant_id: str,
    zi: Annotated[dt.date, Form()],
    satisfactie: Annotated[int, Form(ge=1, le=5)],
    minute_om: Annotated[int, Form(ge=0, le=10_000)] = 0,
    frictiuni: Annotated[str, Form(max_length=4000)] = "",
) -> Response:
    try:
        pilot.feedback(db, _id(tenant_id), zi=zi, satisfactie=satisfactie, minute_om=minute_om,
                       frictiuni=frictiuni, utilizator_id=u.utilizator_id)  # fmt: skip
    except pilot.PilotInvalid as exc:
        return RedirectResponse(f"/lansare/pilot?eroare={exc}", status_code=303)
    return _inapoi("feedback")


@router.post("/pilot/{tenant_id}/incident", dependencies=[Depends(csrf_protect)])
def incident(
    u: Proprietar, db: DbSession, tenant_id: str, descriere: Annotated[str, Form(max_length=300)] = ""
) -> Response:
    try:
        pilot.raporteaza_incident(db, _id(tenant_id), descriere=descriere, utilizator_id=u.utilizator_id)
    except pilot.PilotInvalid as exc:
        return RedirectResponse(f"/lansare/pilot?eroare={exc}", status_code=303)
    return _inapoi("incident")


@router.post("/pilot/raport", dependencies=[Depends(csrf_protect)])
def raport(u: Proprietar, db: DbSession) -> Response:
    pilot.raport_saptamanal(db, dt.datetime.now(dt.UTC).date())
    return _inapoi("raport")
