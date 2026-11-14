"""Portalul (F7.5, docs/19 §19.2): materialele (încărcare cu verificarea tipului după conținut) și inboxul de
tendințe. Fișierul intră în biblioteca de active cu sursa `portal` și cu cine l-a încărcat."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response

from app import media
from app.conturi import DbSession, SesiuneCurenta, csrf_protect, require_role
from app.conturi.roluri import Rol
from app.panou.sabloane import pagina
from app.portal import progres
from app.portal.web import tenant

router = APIRouter(prefix="/portal", tags=["portal"])
# Vizitatorul doar citește rapoarte; încarcă titularul și aprobatorul.
PoateIncarca = Annotated[SesiuneCurenta, Depends(require_role(Rol.CLIENT_TITULAR, Rol.CLIENT_APROBATOR))]
LIMITA_CITIRE = 300 * 1024 * 1024 + 1
MESAJE = {"incarcat": "Fișierul a fost adăugat în biblioteca ta.", "tendinta": "Mulțumim! Am notat ideea."}


def _pagina(
    request: Request, u: SesiuneCurenta, db: DbSession, *, status: int = 200, **extra: object
) -> Response:
    t = tenant(u)
    return pagina(
        request,
        u,
        "portal/materiale.html",
        tab="materiale",
        status=status,
        active=media.biblioteca.ale_clientului(db, t),
        tendinte=media.tendinte.ale_clientului(db, t),
        **extra,
    )


@router.get("/materiale")
def materiale(request: Request, u: PoateIncarca, db: DbSession, mesaj: str = "") -> Response:
    return _pagina(request, u, db, mesaj=MESAJE.get(mesaj, ""))


@router.post("/materiale", dependencies=[Depends(csrf_protect)])
async def incarca(
    request: Request,
    u: PoateIncarca,
    db: DbSession,
    fisier: Annotated[UploadFile, File()],
    descriere: Annotated[str, Form(max_length=500)] = "",
) -> Response:
    corp = await fisier.read(LIMITA_CITIRE)
    try:
        media.biblioteca.incarca(
            db,
            tenant(u),
            corp,
            nume_original=fisier.filename or "fisier",
            sursa="portal",
            utilizator_id=u.utilizator_id,
            descriere=descriere,
        )
    except media.biblioteca.FisierRefuzat as exc:
        return _pagina(request, u, db, status=422, eroare=f"Fișierul nu a fost încărcat: {exc}.")
    return RedirectResponse("/portal/materiale?mesaj=incarcat", status_code=303)


@router.post("/tendinte", dependencies=[Depends(csrf_protect)])
def tendinta(
    request: Request, u: PoateIncarca, db: DbSession, text: Annotated[str, Form(max_length=2000)]
) -> Response:
    try:
        media.tendinte.adauga(db, tenant(u), text, utilizator_id=u.utilizator_id)
    except media.tendinte.TendintaInvalida as exc:
        db.rollback()
        return _pagina(request, u, db, status=422, eroare=f"Nu s-a salvat: {exc}.")
    return RedirectResponse("/portal/materiale?mesaj=tendinta", status_code=303)


progres.inregistreaza_pas(
    "materiale",
    lambda db, t: progres.Pas(
        3,
        "Încarcă logo, fotografii și liste de prețuri",
        bool(media.biblioteca.ale_clientului(db, t, limita=1)),
        "/portal/materiale",
    ),
)
