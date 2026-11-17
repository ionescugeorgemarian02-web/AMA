"""Ecranul „Reclame” (docs/16 §16.10, docs/18): conturile de reclame, cifrele față de plafoane, campaniile.

- `/reclame`: conturile active, cu cheltuiala zilei și a lunii față de plafon și totalurile pe 30 de zile.
- `POST /reclame/plan/<id>/{aproba|respinge}`: decizia pe planul media (F13.3), doar proprietarul.
- `/reclame/cont/<id>`: contul, pe campanii și pe zile, cum le arată managerul de reclame (F13.1, F13.2).
Citirea cere `rapoarte.citeste`.
"""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import reclame
from app.conturi import (
    DbSession,
    Permisiune,
    Rol,
    SesiuneCurenta,
    csrf_protect,
    require_permission,
    require_role,
)
from app.conturi.roluri import ROLURI_AGENTIE
from app.panou.sabloane import pagina
from app.reclame import plan, rezultate

router = APIRouter(prefix="/reclame", tags=["reclame"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
Proprietar = Annotated[SesiuneCurenta, Depends(require_role(Rol.PROPRIETAR))]
PoateCiti = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.RAPOARTE_CITESTE))]


def lei(bani: int | None) -> str:
    """1234567 → „12.345,67”: formatul românesc, fără rotunjiri."""
    if bani is None:
        return "–"
    semn = "-" if bani < 0 else ""
    intregi, zecimale = divmod(abs(int(bani)), 100)
    return f"{semn}{intregi:,}".replace(",", ".") + f",{zecimale:02d}"


def _id(text: str) -> uuid.UUID:
    try:
        return uuid.UUID(text)
    except ValueError:
        raise HTTPException(status_code=404, detail="Cont inexistent.") from None


def _azi() -> dt.date:
    return dt.datetime.now(dt.UTC).date()


@router.get("")
def lista(request: Request, u: Agentie, _p: PoateCiti, db: DbSession) -> Response:
    azi = _azi()
    randuri = []
    for c in rezultate.conturi(db):
        randuri.append(
            {
                "cont": c,
                "azi": rezultate.totaluri(db, c.id, azi, azi),
                "luna": rezultate.totaluri(db, c.id, azi.replace(day=1), azi),
                "t30": rezultate.totaluri(db, c.id, azi - dt.timedelta(days=29), azi),
            }
        )
    return pagina(
        request, u, "panou/reclame.html", tab="meniu", randuri=randuri, lei=lei,
        platforme=reclame.ETICHETE_PLATFORME,
    )  # fmt: skip


@router.post("/plan/{plan_id}/{actiune}", dependencies=[Depends(csrf_protect)])
def decide_plan(plan_id: str, actiune: str, u: Proprietar, db: DbSession) -> Response:
    r = db.get(reclame.PlanMediaRand, _id(plan_id))
    if r is None or actiune not in ("aproba", "respinge"):
        raise HTTPException(status_code=404, detail="Plan inexistent.")
    cont_id = r.cont_id
    try:
        plan.decide(db, r.id, aprobat=actiune == "aproba", utilizator_id=u.utilizator_id)
    except plan.PlanRefuzat as exc:
        return RedirectResponse(f"/reclame/cont/{cont_id}?eroare={str(exc)[:300]}", status_code=303)
    return RedirectResponse(f"/reclame/cont/{cont_id}?mesaj=plan_{actiune}", status_code=303)


@router.get("/cont/{cont_id}")
def cont(
    request: Request,
    cont_id: str,
    u: Agentie,
    _p: PoateCiti,
    db: DbSession,
    zile: int = 30,
    mesaj: str = "",
    eroare: str = "",
) -> Response:
    c = db.get(reclame.ContReclame, _id(cont_id))
    if c is None:
        raise HTTPException(status_code=404, detail="Cont inexistent.")
    zile = max(1, min(zile, 90))
    azi = _azi()
    de_la = azi - dt.timedelta(days=zile - 1)
    return pagina(
        request, u, "panou/reclame_cont.html", tab="meniu", cont=c, lei=lei, zile=zile, de_la=de_la,
        pana_la=azi,
        total=rezultate.totaluri(db, c.id, de_la, azi),
        campanii=rezultate.pe_obiecte(db, c.id, de_la, azi),
        pe_zile=rezultate.pe_zile(db, c.id, de_la, azi),
        platforme=reclame.ETICHETE_PLATFORME,
        planuri=plan.ale_contului(db, c.id),
        mesaj=mesaj,
        eroare=eroare,
    )  # fmt: skip
