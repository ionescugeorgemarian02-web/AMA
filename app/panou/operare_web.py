"""Pagina Operare (doar proprietarul): livrare (F1.8) și starea backup-ului (F1.9)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response

from app.conturi import DbSession, SesiuneCurenta, csrf_protect, require_role
from app.conturi.roluri import Rol
from app.operare import backup, livrare
from app.panou.sabloane import pagina

router = APIRouter(prefix="/operare", tags=["operare"])
Proprietar = Annotated[SesiuneCurenta, Depends(require_role(Rol.PROPRIETAR))]

MESAJE = {
    "promovare": "Promovarea a fost cerută. Deployer-ul o preia în câteva secunde.",
    "revenire": "Revenirea a fost cerută. Deployer-ul o preia în câteva secunde.",
}


def _pagina(
    request: Request, u: SesiuneCurenta, db: DbSession, *, status: int = 200, **extra: object
) -> Response:
    return pagina(
        request,
        u,
        "panou/operare.html",
        tab="meniu",
        status=status,
        livrare=livrare.citeste_stare(db),
        backup=backup.citeste_stare(),
        **extra,
    )


@router.get("")
def operare(request: Request, u: Proprietar, db: DbSession, mesaj: str = "") -> Response:
    return _pagina(request, u, db, mesaj=MESAJE.get(mesaj, ""))


@router.get("/confirma")
def confirma(
    request: Request, u: Proprietar, db: DbSession, actiune: Literal["promovare", "revenire"]
) -> Response:
    stare = livrare.citeste_stare(db, istoric=1)
    if actiune == "promovare":
        v, titlu, buton, actiune_url = (
            stare.disponibila,
            "Promovare în producție",
            "Da, promovează",
            "/operare/promoveaza",
        )
        intrebare = "Promovezi în producție versiunea de pe staging?"
    else:
        v, titlu, buton, actiune_url = stare.anterioara, "Revenire", "Da, revino", "/operare/revino"
        intrebare = "Revii la versiunea anterioară din producție?"
    if v is None:
        return _pagina(
            request, u, db, status=409, eroare="Nu există o versiune potrivită pentru această acțiune."
        )
    return pagina(
        request,
        u,
        "panou/confirmare.html",
        tab="meniu",
        titlu=titlu,
        intrebare=f"{intrebare} Versiunea: {v.versiune or v.imagine[-12:]}.",
        detalii="Deployer-ul pornește versiunea lângă cea veche și mută traficul doar după verificări; "
        "dacă ceva se strică, revine singur. Acțiunea rămâne în jurnalul de audit.",
        actiune=actiune_url,
        ascunse={},
        buton=buton,
        periculos=True,
        anulare="/operare",
    )


@router.post("/promoveaza", dependencies=[Depends(csrf_protect)])
def promoveaza(
    request: Request, u: Proprietar, db: DbSession, confirmare: Annotated[Literal["da"], Form()]
) -> Response:
    try:
        livrare.cere_promovare(db, u.utilizator_id)
    except livrare.EroareLivrare as exc:
        return _pagina(request, u, db, status=409, eroare=str(exc))
    return RedirectResponse("/operare?mesaj=promovare", status_code=303)


@router.post("/revino", dependencies=[Depends(csrf_protect)])
def revino(
    request: Request, u: Proprietar, db: DbSession, confirmare: Annotated[Literal["da"], Form()]
) -> Response:
    try:
        livrare.cere_revenire(db, u.utilizator_id)
    except livrare.EroareLivrare as exc:
        return _pagina(request, u, db, status=409, eroare=str(exc))
    return RedirectResponse("/operare?mesaj=revenire", status_code=303)
