"""Ecran Shopify doar pentru tenantul activ autorizat."""

import datetime as dt
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.comert import atribuire, catalog
from app.comert.modele import Magazin, Sincronizare
from app.conturi import Permisiune, SesiuneCurenta, require_permission
from app.db import sesiune_tenant

router = APIRouter(prefix="/comert", tags=["comert"])
Sabloane = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
Cititor = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.RAPOARTE_CITESTE))]


@router.get("")
def ecran(request: Request, u: Cititor) -> Response:
    if u.tenant_id is None:
        raise HTTPException(400, "Selectează un client activ.")
    with sesiune_tenant(u.tenant_id) as db:
        magazine = list(db.scalars(select(Magazin).order_by(Magazin.magazin)))
        stari = {
            s.magazin: f"{s.stare} · {s.ultima_reusita or 'fără reușită'}"
            for s in db.scalars(select(Sincronizare))
        }
        # Doar date publice ale stării, niciodată tokenul în contextul șablonului.
        publice = [{"magazin": m.magazin, "token_criptat": m.token_criptat is not None} for m in magazine]
    return Sabloane.TemplateResponse(
        request=request,
        name="magazin.html",
        context={
            "magazine": publice,
            "stari": stari,
            "produse": {m.magazin: len(catalog.lista(u.tenant_id, m.magazin)) for m in magazine},
            "rapoarte": {
                m.magazin: atribuire.raport_lunar(u.tenant_id, m.magazin, dt.datetime.now(dt.UTC).date(), {})
                for m in magazine
            },
        },
    )
