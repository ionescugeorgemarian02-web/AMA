"""Portalul: prompterul pentru formatul E (F8.12, docs/14 §14.1). Clientul își citește scriptul de pe
telefon (text
mare, defilare lentă, fără JavaScript), se filmează și încarcă filmarea brută; platforma taie pauzele, pune
subtitrări și aduce sunetul la nivel, ca job pe culoarele grele."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response

from app import media, validare
from app.conturi import DbSession, SesiuneCurenta, csrf_protect, require_role
from app.conturi.roluri import Rol
from app.panou.sabloane import pagina
from app.portal.web import tenant

router = APIRouter(prefix="/portal", tags=["portal"])
PoateFilma = Annotated[SesiuneCurenta, Depends(require_role(Rol.CLIENT_TITULAR, Rol.CLIENT_APROBATOR))]
VITEZE = {"lent": "prompter-lent", "normal": "prompter-normal", "rapid": "prompter-rapid"}
LIMITA_CITIRE = 300 * 1024 * 1024 + 1


def _script(db: DbSession, lid: uuid.UUID) -> list[str]:
    try:
        c = validare.continut.citeste(db, lid)
    except validare.FaraContinut as exc:
        raise HTTPException(404) from exc
    fraze = media.regizor.fraze_din_script(c.campuri) if c.campuri.get("batai") else [c.text]
    return [f for f in fraze if f]


@router.get("/prompter/{lid}")
def prompter(
    request: Request, u: PoateFilma, db: DbSession, lid: uuid.UUID, viteza: str = "normal", mesaj: str = ""
) -> Response:
    return pagina(
        request,
        u,
        "portal/prompter.html",
        tab="materiale",
        fraze=_script(db, lid),
        lid=lid,
        clasa=VITEZE.get(viteza, VITEZE["normal"]),
        viteza=viteza,
        mesaj="Am primit filmarea. Clipul apare în materiale după montaj." if mesaj == "trimis" else "",
    )


@router.post("/prompter/{lid}", dependencies=[Depends(csrf_protect)])
async def filmare(
    request: Request, u: PoateFilma, db: DbSession, lid: uuid.UUID, fisier: Annotated[UploadFile, File()]
) -> Response:
    _script(db, lid)
    corp = await fisier.read(LIMITA_CITIRE)
    try:
        a = media.biblioteca.incarca(
            db,
            tenant(u),
            corp,
            nume_original=fisier.filename or "filmare.mp4",
            sursa="portal",
            utilizator_id=u.utilizator_id,
            descriere=f"filmare brută, format E, pentru {lid}",
        )
    except media.biblioteca.FisierRefuzat as exc:
        raise HTTPException(422, str(exc)) from exc
    if a.categorie != "video":
        raise HTTPException(422, "încarcă o filmare (MP4 sau MOV)")
    db.commit()
    media.fluxuri.trimite_format_e(tenant(u), a.id, lid)
    return RedirectResponse(f"/portal/prompter/{lid}?mesaj=trimis", status_code=303)
