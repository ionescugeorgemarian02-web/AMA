"""Rutele publice ale publicării (F9): fișierele servite platformelor prin linkuri semnate (F9.3)."""

import mimetypes
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app import media, productie
from app.conturi import DbSession, Permisiune, SesiuneCurenta, require_permission
from app.publicare import linkuri

router = APIRouter(tags=["publicare"])


@router.get(linkuri.PREFIX + "{jeton}")
def fisier(jeton: str) -> FileResponse:
    cale = linkuri.verifica(jeton)
    if cale is None:
        raise HTTPException(status_code=404)
    return FileResponse(cale, media_type=mimetypes.guess_type(cale.name)[0] or "application/octet-stream")


@router.get("/aprobari-media/{cerere}/video")
def previzualizare(
    cerere: uuid.UUID,
    db: DbSession,
    u: Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.LIVRABIL_APROBA))],
) -> FileResponse:
    ap = db.get(productie.Aprobare, cerere)
    if ap is None:
        raise HTTPException(status_code=404)
    activ = media.montaj.video_verificat(db, ap.tenant_id, ap.livrabil_id, ap.versiune)
    if activ is None or not media.regizor.cale(activ).is_file():
        raise HTTPException(status_code=404, detail="Exportul versiunii nu este disponibil.")
    return FileResponse(media.regizor.cale(activ), media_type="video/mp4")
