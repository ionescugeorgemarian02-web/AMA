"""Biroul de aprobări (F5.9, docs/18 §18.3; înlocuiește punctul minim din F2.8), întâi pentru telefon.

Lista cererilor în așteptare după urgență, termen și prioritate; pe fiecare card: textul așa cum apare pe
canal, verdictele
și dovezile ultimei validări, pachetul de context (faptele și ofertele aprobate), istoricul versiunilor cu
diferențele și
întrebările deschise către client. Acțiuni: aprobă; respinge cu motiv standard (listă ca date) și, opțional, o
frază;
editează pe loc (versiune nouă, care trece din nou validarea: nicio aprobare pe o versiune nevalidată);
răspunde la o
întrebare către client. Fiecare cu CSRF, permisiunea `livrabil.aproba`, dreptul pe decident și audit. Decizia
se leagă de
versiunea văzută de om. Statistica motivelor de respingere stă sub listă. Aprobarea în grup rămâne o propunere
(F6).
"""

import datetime as dt
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
from app.validare import birou, intrebari
from app.validare import trimite as trimite_validare

router = APIRouter(prefix="/aprobari", tags=["aprobari"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
PoateAproba = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.LIVRABIL_APROBA))]
PoateEdita = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.LIVRABIL_EDITEAZA))]
SoloAgentie = Depends(require_role(*ROLURI_AGENTIE))  # portalul clientului (F7) va avea rutele lui

MESAJE = {
    "aprobat": "Aprobarea a fost înregistrată. Livrabilul poate merge mai departe.",
    "respins": "Respingerea a fost înregistrată, cu motivul tău.",
    "editat": "Versiunea nouă a fost salvată și trece din nou validarea; revine aici dacă trece.",
    "raspuns": "Răspunsul a fost salvat; faptul intră în Creier după aprobarea unui om.",
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
    carduri = [] if toate else birou.coada(db, dt.datetime.now(dt.UTC))
    poate = {c.aprobare.id: productie.poate_decide(u.rol, Decident(c.aprobare.decident)) for c in carduri}
    return pagina(
        request,
        u,
        "panou/aprobari.html",
        carduri=carduri,
        poate=poate,
        statistica_motive=birou.statistica_motive(db),
        etichete_livrabil={k.value: v for k, v in ETICHETE_LIVRABIL.items()},
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
    except (
        aprobari.DejaDecisa,
        aprobari.VersiuneVeche,
        aprobari.NivelUmbra,
        aprobari.VersiuneNevalidata,
    ) as exc:
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


@router.post("/{id_cerere}/editeaza", dependencies=[SoloAgentie, Depends(csrf_protect)])
def editeaza(
    request: Request,
    u: PoateEdita,
    db: DbSession,
    id_cerere: str,
    versiune: Annotated[int, Form(ge=1)],
    text: Annotated[str, Form(max_length=20000)],
) -> Response:
    ap = aprobari.citeste(db, _id(id_cerere))
    if ap is None:
        raise HTTPException(status_code=404, detail="Cererea nu există.")
    if not productie.poate_decide(u.rol, Decident(ap.decident)):
        raise HTTPException(status_code=403, detail="Nu ai dreptul să editezi această cerere.")
    try:
        lv = birou.editeaza(db, ap.id, versiune=versiune, text=text, utilizator_id=u.utilizator_id)
    except birou.EditareInvalida as exc:
        return _pagina(request, u, db, status=409, eroare=str(exc))
    db.commit()  # versiunea nouă și starea `în validare` sunt în bază înainte ca jobul să le citească
    trimite_validare(lv.tenant_id, lv.id, cheie=f"validare:{lv.id}:{lv.versiune}")
    return RedirectResponse("/aprobari?mesaj=editat", status_code=303)


@router.post("/intrebari/{id_intrebare}/raspunde", dependencies=[SoloAgentie, Depends(csrf_protect)])
def raspunde(
    request: Request,
    u: PoateAproba,
    db: DbSession,
    id_intrebare: str,
    raspuns: Annotated[str, Form(max_length=2000)],
) -> Response:
    try:
        intrebari.raspunde(db, _id(id_intrebare), raspuns, utilizator_id=u.utilizator_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Întrebarea nu există.") from None
    except ValueError as exc:  # întrebare închisă sau răspuns gol
        return _pagina(request, u, db, status=422, eroare=str(exc))
    return RedirectResponse("/aprobari?mesaj=raspuns", status_code=303)
