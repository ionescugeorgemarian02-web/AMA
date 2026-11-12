"""Punctul minim din panou pentru aprobări (F2.8): lista cererilor și două acțiuni, „Aprobă” și „Respinge”.

Ecranul complet (card cu previzualizare, verdicte, aprobare în grup, editare pe loc) este F5. Aici: lista
simplă a cererilor, cu termen și versiune, și acțiunile, fiecare cu CSRF, permisiune (`livrabil.aproba`),
verificarea dreptului pe decident (operator / client) și audit (scris de `productie.aprobari`). Decizia se
leagă de versiunea văzută de om: dacă livrabilul s-a schimbat între timp, decizia este refuzată.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import productie
from app.conturi import (
    DbSession,
    Permisiune,
    SesiuneCurenta,
    csrf_protect,
    require_permission,
    require_role,
)
from app.conturi.roluri import ROLURI_AGENTIE
from app.panou.sabloane import pagina
from app.productie import aprobari
from app.productie.reguli_aprobare import (
    ETICHETE_DECIDENT,
    ETICHETE_STARE,
    MOTIVE_RESPINGERE,
    Decident,
    Hotarare,
)
from app.productie.stari import ETICHETE as ETICHETE_LIVRABIL
from app.productie.stari import Stare

router = APIRouter(prefix="/aprobari", tags=["aprobari"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
PoateAproba = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.LIVRABIL_APROBA))]
SoloAgentie = Depends(require_role(*ROLURI_AGENTIE))  # portalul clientului (F7) va avea rutele lui

MESAJE = {
    "aprobat": "Aprobarea a fost înregistrată. Livrabilul poate merge mai departe.",
    "respins": "Respingerea a fost înregistrată, cu motivul tău.",
}


def _pagina(
    request: Request,
    u: SesiuneCurenta,
    db: DbSession,
    *,
    toate: bool = False,
    status: int = 200,
    **extra: object,
) -> Response:
    randuri = [
        {
            "a": a,
            "livrabil": liv,
            "poate": productie.poate_decide(u.rol, Decident(a.decident)) and a.stare == "in_asteptare",
            "stare_livrabil": ETICHETE_LIVRABIL[Stare(liv.stare)],
        }
        for a, liv in aprobari.listeaza(db, doar_in_asteptare=not toate)
    ]
    return pagina(
        request,
        u,
        "panou/aprobari.html",
        tab="aprobari",
        status=status,
        randuri=randuri,
        toate=toate,
        etichete_aprobare=ETICHETE_STARE,
        etichete_decident=ETICHETE_DECIDENT,
        motive=MOTIVE_RESPINGERE,
        **extra,
    )


@router.get("")
def lista(
    request: Request, u: Agentie, db: DbSession, stare: str = "in_asteptare", mesaj: str = ""
) -> Response:
    return _pagina(request, u, db, toate=stare == "toate", mesaj=MESAJE.get(mesaj, ""))


def _id(valoare: str) -> uuid.UUID:
    try:
        return uuid.UUID(valoare)
    except ValueError:
        raise HTTPException(status_code=404, detail="Cererea nu există.") from None


def _decide(
    request: Request,
    u: SesiuneCurenta,
    db: DbSession,
    id_cerere: str,
    hotarare: Hotarare,
    *,
    versiune: int,
    motiv_standard: str = "",
    motiv: str = "",
) -> Response:
    try:
        r = aprobari.decide(
            db,
            _id(id_cerere),
            hotarare,
            utilizator_id=u.utilizator_id,
            rol=u.rol,
            versiune=versiune,
            motiv_standard=motiv_standard or None,
            motiv=motiv,
        )
    except aprobari.AprobareInexistenta:
        raise HTTPException(status_code=404, detail="Cererea nu există.") from None
    except aprobari.FaraDrept:
        raise HTTPException(status_code=403, detail="Nu ai dreptul să decizi această cerere.") from None
    except aprobari.MotivLipsa as exc:
        return _pagina(request, u, db, status=422, eroare=str(exc))
    except (aprobari.DejaDecisa, aprobari.VersiuneVeche) as exc:
        return _pagina(request, u, db, status=409, eroare=str(exc))
    if not r.aplicat:
        return _pagina(
            request,
            u,
            db,
            status=409,
            eroare="Termenul cererii a trecut: a expirat, nu a fost aprobată. Livrabilul se reprogramează.",
        )
    return RedirectResponse(f"/aprobari?mesaj={hotarare.value}", status_code=303)


@router.post("/{id_cerere}/aproba", dependencies=[SoloAgentie, Depends(csrf_protect)])
def aproba(
    request: Request, u: PoateAproba, db: DbSession, id_cerere: str, versiune: Annotated[int, Form(ge=1)]
) -> Response:
    return _decide(request, u, db, id_cerere, Hotarare.APROBAT, versiune=versiune)


@router.post("/{id_cerere}/respinge", dependencies=[SoloAgentie, Depends(csrf_protect)])
def respinge(
    request: Request,
    u: PoateAproba,
    db: DbSession,
    id_cerere: str,
    versiune: Annotated[int, Form(ge=1)],
    motiv_standard: Annotated[str, Form(max_length=40)] = "",
    motiv: Annotated[str, Form(max_length=300)] = "",
) -> Response:
    return _decide(
        request,
        u,
        db,
        id_cerere,
        Hotarare.RESPINS,
        versiune=versiune,
        motiv_standard=motiv_standard,
        motiv=motiv,
    )
