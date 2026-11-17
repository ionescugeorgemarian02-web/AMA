"""Ecranul „Reclame” (docs/16 §16.10, docs/18): conturile de reclame, cifrele față de plafoane, campaniile.

- `/reclame`: conturile active, cu cheltuiala zilei și a lunii față de plafon și totalurile pe 30 de zile.
- `POST /reclame/plan/<id>/{aproba|respinge}`: decizia pe planul media (F13.3), doar proprietarul.
- `POST /reclame/campanie/<id>/{activeaza|pauza}` și `POST
/reclame/propunere/<id>/{aproba|respinge|anuleaza}`:
  schimbările (F13.4); anularea aplică imediat starea de dinainte. Doar proprietarul.
- `/reclame/consiliu`: dosarele de Consiliu (F13.7); dosarul se copiază în Claude, decizia se lipește înapoi.
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
from app.reclame import consiliu, constructor, plan, propuneri, rezultate, strateg

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
        request,
        u,
        "panou/reclame.html",
        tab="meniu",
        randuri=randuri,
        lei=lei,
        platforme=reclame.ETICHETE_PLATFORME,
    )


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
    propuneri.reconciliaza(db)
    c = db.get(reclame.ContReclame, _id(cont_id))
    if c is None:
        raise HTTPException(status_code=404, detail="Cont inexistent.")
    zile = max(1, min(zile, 90))
    azi = _azi()
    de_la = azi - dt.timedelta(days=zile - 1)
    return pagina(
        request,
        u,
        "panou/reclame_cont.html",
        tab="meniu",
        cont=c,
        lei=lei,
        zile=zile,
        de_la=de_la,
        pana_la=azi,
        total=rezultate.totaluri(db, c.id, de_la, azi),
        campanii=rezultate.pe_obiecte(db, c.id, de_la, azi),
        pe_zile=rezultate.pe_zile(db, c.id, de_la, azi),
        platforme=reclame.ETICHETE_PLATFORME,
        planuri=plan.ale_contului(db, c.id),
        campanii_construite=constructor.campanii(db, c.id),
        propuneri_cont=propuneri.ale_contului(db, c.id),
        etichete_stare=propuneri.ETICHETE_STARE,
        decizii=strateg.ale_contului(db, c.id),
        mesaj=mesaj,
        eroare=eroare,
    )


MESAJE_SCHIMBARI = {"activeaza": "activa", "pauza": "pauza"}


def _inapoi(cont_id: uuid.UUID, mesaj: str = "", eroare: str = "") -> RedirectResponse:
    q = f"eroare={eroare[:300]}" if eroare else f"mesaj={mesaj}"
    return RedirectResponse(f"/reclame/cont/{cont_id}?{q}", status_code=303)


@router.post("/campanie/{campanie_id}/{actiune}", dependencies=[Depends(csrf_protect)])
def schimba_starea(campanie_id: str, actiune: str, u: Proprietar, db: DbSession) -> Response:
    c = db.get(reclame.Campanie, _id(campanie_id))
    if c is None or actiune not in MESAJE_SCHIMBARI:
        raise HTTPException(status_code=404, detail="Campanie inexistentă.")
    try:
        p = propuneri.propune(
            db,
            c.id,
            "stare",
            {"stare": MESAJE_SCHIMBARI[actiune]},
            sursa="om",
            utilizator_id=u.utilizator_id,
            motiv="Activată de proprietar" if actiune == "activeaza" else "Pusă pe pauză de proprietar",
        )
        if p.stare != "propusa":
            return _inapoi(c.cont_id, eroare="; ".join(p.verdict.get("motive", [])) or "schimbare refuzată")
        propuneri.aproba(db, p.id, utilizator_id=u.utilizator_id)
    except propuneri.PropunereRefuzata as exc:
        return _inapoi(c.cont_id, eroare=str(exc))
    return _inapoi(c.cont_id, f"campanie_{actiune}")


@router.post("/propunere/{propunere_id}/{actiune}", dependencies=[Depends(csrf_protect)])
def decide_propunere(propunere_id: str, actiune: str, u: Proprietar, db: DbSession) -> Response:
    p = db.get(reclame.Propunere, _id(propunere_id))
    if p is None or actiune not in ("aproba", "respinge", "anuleaza"):
        raise HTTPException(status_code=404, detail="Propunere inexistentă.")
    cont_id = p.cont_id
    try:
        if actiune == "aproba":
            propuneri.aproba(db, p.id, utilizator_id=u.utilizator_id)
        elif actiune == "respinge":
            propuneri.respinge(db, p.id, utilizator_id=u.utilizator_id)
        else:
            inv = propuneri.anuleaza(db, p.id, utilizator_id=u.utilizator_id)
            if inv.stare == "refuzata":
                return _inapoi(cont_id, eroare="; ".join(inv.verdict.get("motive", [])))
    except propuneri.PropunereRefuzata as exc:
        return _inapoi(cont_id, eroare=str(exc))
    return _inapoi(cont_id, f"propunere_{actiune}")


# --- Consiliul (F13.7): dosarul se deschide în Claude, decizia se lipește înapoi
@router.get("/consiliu")
def consiliu_lista(request: Request, u: Proprietar, db: DbSession, mesaj: str = "") -> Response:
    return pagina(
        request,
        u,
        "panou/reclame_consiliu.html",
        tab="meniu",
        dosare=consiliu.dosare(db),
        conturi=rezultate.conturi(db),
        dosar=None,
        mesaj=mesaj,
        eroare="",
    )


@router.post("/consiliu/deschide", dependencies=[Depends(csrf_protect)])
async def consiliu_deschide(request: Request, u: Proprietar, db: DbSession) -> Response:
    f = await request.form()
    try:
        d = consiliu.deschide(
            db,
            _id(str(f.get("cont_id") or "")),
            subiect=str(f.get("subiect") or "Revizuirea lunară a reclamelor").strip(),
            motiv_apel=str(
                f.get("motiv") or "Revizuirea lunară a strategiei (7.6), cu miză pe buget"
            ).strip(),
        )
    except consiliu.DosarRefuzat as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return RedirectResponse(f"/reclame/consiliu/{d.id}", status_code=303)


@router.get("/consiliu/{dosar_id}")
def consiliu_dosar(
    request: Request, dosar_id: str, u: Proprietar, db: DbSession, eroare: str = ""
) -> Response:
    d = db.get(reclame.DosarConsiliu, _id(dosar_id))
    if d is None:
        raise HTTPException(status_code=404, detail="Dosar inexistent.")
    return pagina(
        request,
        u,
        "panou/reclame_consiliu.html",
        tab="meniu",
        dosar=d,
        dosare=[],
        conturi=[],
        mesaj="",
        eroare=eroare,
    )


@router.post("/consiliu/{dosar_id}/importa", dependencies=[Depends(csrf_protect)])
async def consiliu_importa(request: Request, dosar_id: str, u: Proprietar, db: DbSession) -> Response:
    did = _id(dosar_id)
    text = str((await request.form()).get("raspuns") or "")
    try:
        rec = consiliu.importa(db, did, text, utilizator_id=u.utilizator_id)
    except (consiliu.DosarRefuzat, propuneri.PropunereRefuzata) as exc:
        return RedirectResponse(f"/reclame/consiliu/{did}?eroare={str(exc)[:300]}", status_code=303)
    return RedirectResponse(f"/reclame/cont/{rec.cont_id}?mesaj=decizie_consiliu", status_code=303)
