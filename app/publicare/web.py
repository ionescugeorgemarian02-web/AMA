"""Rutele publice ale publicării (F9): fișierele servite platformelor prin linkuri semnate (F9.3)."""

import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.publicare import linkuri

router = APIRouter(tags=["publicare"])


@router.get(linkuri.PREFIX + "{jeton}")
def fisier(jeton: str) -> FileResponse:
    cale = linkuri.verifica(jeton)
    if cale is None:
        raise HTTPException(status_code=404)
    return FileResponse(cale, media_type=mimetypes.guess_type(cale.name)[0] or "application/octet-stream")
