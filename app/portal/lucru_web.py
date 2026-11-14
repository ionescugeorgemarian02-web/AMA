"""Portalul (F7.4, docs/19 §19.2, §19.4): Creierul de brand, calendarul și aprobările clientului, de pe
telefon.

- Creier: intrările clientului cu versiunea aprobată și propunerile care îi așteaptă aprobarea (titularul
aprobă).
- Calendar: ce urmează, pe canal, din calendarul aprobat.
- Aprobări: cererile adresate clientului, cu previzualizarea reală (textul versiunii de aprobat); „Aprobă
tot lotul”
  aprobă dintr-o atingere toate cererile afișate, fiecare pe versiunea văzută (o versiune schimbată între timp
  e refuzată, nu aprobată pe nevăzute). Respingerea cere un motiv. Totul prin `productie.aprobari.decide`
  (dreptul rolului, termenul, validarea versiunii, auditul cu utilizator, moment și versiune).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import continut, creier, productie, validare
from app.conturi import (
    DbSession,
    Permisiune,
    SesiuneCurenta,
    csrf_protect,
    poate,
    require_permission,
    require_role,
)
from app.conturi.roluri import ROLURI_CLIENT
from app.panou.sabloane import pagina
from app.portal.web import tenant

router = APIRouter(prefix="/portal", tags=["portal"])
Client = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_CLIENT))]
PoateAproba = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.LIVRABIL_APROBA))]
PoateEdita = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.CREIER_EDITEAZA))]
MESAJE = {
    "lot": "Lotul a fost aprobat.",
    "aprobat": "Aprobat.",
    "respins": "Respins; echipa primește motivul.",
    "creier": "Versiunea a fost aprobată.",
}
ETICHETE_COMP = {
    "brief": "Brieful firmei",
    "profil_brand": "Ghidul de brand",
    "registru_fapte": "Fapte",
    "strategie": "Planul pe 90 de zile",
    "insight_public": "Publicul",
    "insight_piata": "Piața",
    "catalog_oferte": "Oferte",
}


# --- Creierul de brand -------------------------------------------------------------------------------------


@router.get("/creier")
def creierul(request: Request, u: Client, db: DbSession, mesaj: str = "") -> Response:
    t = tenant(u)
    intrari = []
    for i, v in creier.lista(db, tenant_id=t):
        if i.compartiment not in ETICHETE_COMP:
            continue
        propuse = [x for x in creier.istoric(db, i.id) if x.stare == "propus"]
        intrari.append((i, v, propuse[-1] if propuse else None))
    return pagina(
        request,
        u,
        "portal/creier.html",
        tab="acasa",
        intrari=intrari,
        etichete=ETICHETE_COMP,
        poate_aproba=poate(u.rol, Permisiune.CREIER_EDITEAZA),
        mesaj=MESAJE.get(mesaj, ""),
    )


@router.post("/creier/{intrare_id}/aproba", dependencies=[Depends(csrf_protect)])
def aproba_creier(
    u: PoateEdita, db: DbSession, intrare_id: str, versiune: Annotated[int, Form(ge=1)]
) -> Response:
    try:
        iid = uuid.UUID(intrare_id)
        creier.aproba(db, iid, versiune, utilizator_id=u.utilizator_id)
    except (ValueError, creier.RegulaCreier) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=f"Nu s-a aprobat: {exc}") from None
    return RedirectResponse("/portal/creier?mesaj=creier", status_code=303)


# --- Calendarul ---------------------------------------------------------------------------------------------


@router.get("/calendar")
def calendarul(request: Request, u: Client, db: DbSession) -> Response:
    t = tenant(u)
    sloturi = []
    for cal in continut.calendar.calendare(db, t, limita=2):
        if cal.stare != "aprobat":
            continue
        for i in continut.calendar.intrari(db, cal.id):
            lv = productie.citeste(db, i.livrabil_id) if i.livrabil_id else None
            stare = productie.ETICHETE[productie.Stare(lv.stare)] if lv else "planificat"
            sloturi.append((i, stare))
    sloturi.sort(key=lambda x: x[0].slot_la)
    return pagina(request, u, "portal/calendar.html", tab="calendar", sloturi=sloturi)


# --- Aprobările --------------------------------------------------------------------------------------------


def _ale_clientului(db: DbSession) -> list[tuple[productie.Aprobare, productie.Livrabil, validare.Continut]]:
    rez = []
    for ap, lv in productie.aprobari.listeaza(db):
        if ap.decident != productie.Decident.CLIENT.value:
            continue
        rez.append((ap, lv, validare.continut.citeste(db, lv.id, ap.versiune)))
    return rez


@router.get("/aprobari")
def aprobarile(request: Request, u: Client, db: DbSession, mesaj: str = "", eroare: str = "") -> Response:
    return pagina(
        request,
        u,
        "portal/aprobari.html",
        tab="aprobari",
        cereri=_ale_clientului(db),
        motive=productie.MOTIVE_RESPINGERE,
        mesaj=MESAJE.get(mesaj, ""),
        eroare=eroare,
        poate_aproba=poate(u.rol, Permisiune.LIVRABIL_APROBA),
    )


def _decide(
    db: DbSession,
    u: SesiuneCurenta,
    aprobare_id: uuid.UUID,
    versiune: int,
    hotarare: productie.Hotarare,
    motiv_standard: str | None = None,
    motiv: str = "",
) -> None:
    productie.aprobari.decide(
        db,
        aprobare_id,
        hotarare,
        utilizator_id=u.utilizator_id,
        rol=u.rol,
        versiune=versiune,
        motiv_standard=motiv_standard,
        motiv=motiv,
    )


@router.post("/aprobari/lot", dependencies=[Depends(csrf_protect)])
async def aproba_lotul(request: Request, u: PoateAproba, db: DbSession) -> Response:
    """Aprobă toate cererile afișate: câmpurile `cerere` = `<id>:<versiune>`, exact cum le-a văzut
    clientul."""
    form = await request.form()
    perechi: list[tuple[uuid.UUID, int]] = []
    for v in form.getlist("cerere"):
        text_id, _, text_ver = str(v).partition(":")
        try:
            perechi.append((uuid.UUID(text_id), int(text_ver)))
        except ValueError:
            raise HTTPException(status_code=422, detail="Cerere invalidă.") from None
    if not perechi:
        return RedirectResponse("/portal/aprobari", status_code=303)
    try:
        for aid, ver in perechi:
            _decide(db, u, aid, ver, productie.Hotarare.APROBAT)
    except productie.aprobari.EroareAprobare as exc:
        db.rollback()
        return aprobarile(request, u, db, eroare=f"Lotul nu a fost aprobat: {exc}")
    return RedirectResponse("/portal/aprobari?mesaj=lot", status_code=303)


@router.post("/aprobari/{aprobare_id}/{hotarare}", dependencies=[Depends(csrf_protect)])
def decide_una(
    request: Request,
    u: PoateAproba,
    db: DbSession,
    aprobare_id: str,
    hotarare: str,
    versiune: Annotated[int, Form(ge=1)],
    motiv_standard: Annotated[str, Form()] = "",
    motiv: Annotated[str, Form(max_length=500)] = "",
) -> Response:
    if hotarare not in ("aproba", "respinge"):
        raise HTTPException(status_code=404, detail="Nu există.")
    try:
        aid = uuid.UUID(aprobare_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Nu există.") from None
    h = productie.Hotarare.APROBAT if hotarare == "aproba" else productie.Hotarare.RESPINS
    try:
        _decide(db, u, aid, versiune, h, motiv_standard or None, motiv)
    except productie.aprobari.EroareAprobare as exc:
        db.rollback()
        return aprobarile(request, u, db, eroare=str(exc))
    return RedirectResponse(
        f"/portal/aprobari?mesaj={'aprobat' if h is productie.Hotarare.APROBAT else 'respins'}",
        status_code=303,
    )
