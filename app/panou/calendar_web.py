"""Ecranul „Calendar” (F6.1, docs/18 §18.2, ecranul 8): calendarul de conținut pe client — propunerea
strategului
(D3), sloturile și decizia unui om (aprobă / respinge cu motiv). Întâi pentru telefon: o listă, fără tabele.

CSRF pe orice schimbare; `onboarding.completeaza` pentru a cere o propunere, `creier.editeaza` pentru decizie
(calendarul
pleacă din strategia aprobată și creează livrabilele). Auditul îl scrie serviciul.
"""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import continut, creier, productie
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
from app.panou.sabloane import pagina

router = APIRouter(prefix="/calendar", tags=["calendar"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
PoateDecide = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.CREIER_EDITEAZA))]
PoatePropune = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.ONBOARDING_COMPLETEAZA))]
MESAJE = {
    "aprobat": "Calendarul a fost aprobat; sloturile au devenit livrabile planificate.",
    "respins": "Calendarul a fost respins, cu motivul tău.",
    "pornit": "Calendarul se pregătește (modelul poate amâna). Reîncarcă pagina peste câteva secunde.",
}
STARI = {"propus": "în așteptare", "aprobat": "aprobat", "respins": "respins", "inlocuit": "înlocuit"}


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


def _pagina(
    request: Request, u: SesiuneCurenta, db: DbSession, client_id: str, *, status: int = 200, **extra: object
) -> Response:
    c = _client(db, client_id)
    randuri = []
    for cal in continut.calendar.calendare(db, c.id):
        sloturi = []
        for i in continut.calendar.intrari(db, cal.id):
            lv = productie.citeste(db, i.livrabil_id) if i.livrabil_id else None
            local = i.slot_la.astimezone(continut.calendar.FUS)
            sloturi.append(
                {"i": i, "local": local, "stare": productie.ETICHETE[productie.Stare(lv.stare)] if lv else ""}
            )
        randuri.append({"cal": cal, "stare": STARI[cal.stare], "sloturi": sloturi})
    return pagina(
        request,
        u,
        "panou/calendar.html",
        tab="meniu",
        status=status,
        client=c,
        calendare=randuri,
        maine=(dt.datetime.now(continut.calendar.FUS).date() + dt.timedelta(days=1)).isoformat(),
        poate_decide=poate(u.rol, Permisiune.CREIER_EDITEAZA),
        poate_propune=poate(u.rol, Permisiune.ONBOARDING_COMPLETEAZA),
        **extra,
    )


@router.get("/{client_id}")
def detaliu(request: Request, u: Agentie, db: DbSession, client_id: str, mesaj: str = "") -> Response:
    return _pagina(request, u, db, client_id, mesaj=MESAJE.get(mesaj, ""))


@router.post("/{client_id}/propune", dependencies=[Depends(csrf_protect)])
def propune(
    request: Request, u: PoatePropune, db: DbSession, client_id: str, inceput: Annotated[str, Form()] = ""
) -> Response:
    c = _client(db, client_id)
    try:
        data = dt.date.fromisoformat(inceput) if inceput else dt.date.today() + dt.timedelta(days=1)
    except ValueError:
        return _pagina(request, u, db, client_id, status=422, eroare="Data de început nu este validă.")
    try:
        continut.calendar.strategia_aprobata(db, c.id)
    except creier.RegulaCreier as exc:
        return _pagina(request, u, db, client_id, status=409, eroare=str(exc))
    db.commit()
    continut.fluxuri.trimite_calendarul(
        c.id, u.utilizator_id, inceput=data, cheie=f"calendar:{c.id}:{uuid.uuid4().hex[:8]}"
    )
    return RedirectResponse(f"/calendar/{c.id}?mesaj=pornit", status_code=303)


@router.post("/{client_id}/{calendar_id}/aproba", dependencies=[Depends(csrf_protect)])
def aproba(request: Request, u: PoateDecide, db: DbSession, client_id: str, calendar_id: str) -> Response:
    c = _client(db, client_id)
    try:
        continut.calendar.aproba(db, _id(calendar_id), utilizator_id=u.utilizator_id)
    except (continut.calendar.EroareCalendar, creier.RegulaCreier) as exc:
        db.rollback()
        return _pagina(request, u, db, client_id, status=409, eroare=str(exc))
    return RedirectResponse(f"/calendar/{c.id}?mesaj=aprobat", status_code=303)


@router.post("/{client_id}/{calendar_id}/respinge", dependencies=[Depends(csrf_protect)])
def respinge(
    request: Request,
    u: PoateDecide,
    db: DbSession,
    client_id: str,
    calendar_id: str,
    motiv: Annotated[str, Form(max_length=300)] = "",
) -> Response:
    c = _client(db, client_id)
    try:
        continut.calendar.respinge(db, _id(calendar_id), utilizator_id=u.utilizator_id, motiv=motiv)
    except continut.calendar.EroareCalendar as exc:
        db.rollback()
        return _pagina(request, u, db, client_id, status=422, eroare=str(exc))
    return RedirectResponse(f"/calendar/{c.id}?mesaj=respins", status_code=303)
