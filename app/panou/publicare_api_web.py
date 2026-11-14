"""Publicarea prin API în panou (F9.6, F9.10, docs/18 ecranul 14 „Publicare”).

- `/publicare/api/tiktok/<livrabil>`: previzualizarea și consimțământul pentru o postare directă pe TikTok
  (regulile de integrare TikTok): contul (pseudonimul, citit chiar acum de la platformă), clipul, legenda,
  vizibilitatea ALEASĂ de om dintre opțiunile contului (fără valoare implicită), interacțiunile, eticheta AI
  și conținutul comercial, bifa de consimțământ explicit. Pagina arată și starea auditului TikTok.
CSRF; permisiunea `livrabil.aproba`; auditul îl scrie serviciul.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import productie, validare
from app.conturi import DbSession, Permisiune, SesiuneCurenta, csrf_protect, require_permission
from app.operare.efecte import autorizare
from app.panou.sabloane import pagina
from app.publicare import canale, consimtamant, fisiere, linkuri

router = APIRouter(prefix="/publicare/api", tags=["publicare"])
PoatePublica = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.LIVRABIL_APROBA))]
ETICHETE_VIZIBILITATE = {
    "PUBLIC_TO_EVERYONE": "Public",
    "MUTUAL_FOLLOW_FRIENDS": "Prieteni (urmăritori reciproci)",
    "FOLLOWER_OF_CREATOR": "Urmăritori",
    "SELF_ONLY": "Doar eu",
}


def _livrabil(db: DbSession, livrabil_id: str) -> productie.Livrabil:
    try:
        lv = productie.citeste(db, uuid.UUID(livrabil_id))
    except ValueError:
        lv = None
    if lv is None or lv.canal != "tiktok":
        raise HTTPException(status_code=404, detail="Nu există.")
    return lv


def _context(db: DbSession, lv: productie.Livrabil) -> dict[str, Any]:
    c = validare.continut.citeste(db, lv.id, lv.versiune)
    f = fisiere.al_continutului(db, c)
    a = canale.aprobare(db, "tiktok", "publicare")
    stare_audit = canale.StareAprobare(a.stare) if a else canale.StareAprobare.NECERUTA
    try:
        creator: dict[str, Any] = autorizare.previzualizare(lv.tenant_id, "tiktok")
        eroare_creator = ""
    except Exception as exc:  # contul neautorizat / platforma indisponibilă: fără consimțământ acum
        creator, eroare_creator = (
            {},
            f"Contul TikTok nu răspunde ({type(exc).__name__}): reautorizează sau reîncearcă.",
        )
    return {
        "lv": lv,
        "text": c.text,
        "creator": creator,
        "eroare_creator": eroare_creator,
        "clip": linkuri.semneaza(f.cale) if f else None,
        "eticheta_ai": bool(f and f.eticheta_ai.get("tiktok")),
        "audit": canale.ETICHETE_APROBARE[stare_audit],
        "etichete_vizibilitate": ETICHETE_VIZIBILITATE,
        "existent": consimtamant.al_versiunii(db, lv.id, lv.versiune, "tiktok"),
    }


@router.get("/tiktok/{livrabil_id}")
def tiktok(request: Request, u: PoatePublica, db: DbSession, livrabil_id: str) -> Response:
    lv = _livrabil(db, livrabil_id)
    return pagina(request, u, "panou/publicare_tiktok.html", tab="meniu", **_context(db, lv))


@router.post("/tiktok/{livrabil_id}", dependencies=[Depends(csrf_protect)])
def tiktok_consimtamant(
    request: Request,
    u: PoatePublica,
    db: DbSession,
    livrabil_id: str,
    vizibilitate: Annotated[str, Form(max_length=40)] = "",
    fara_comentarii: Annotated[bool, Form()] = False,
    fara_duet: Annotated[bool, Form()] = False,
    fara_stitch: Annotated[bool, Form()] = False,
    de_acord: Annotated[bool, Form()] = False,
) -> Response:
    lv = _livrabil(db, livrabil_id)
    ctx = _context(db, lv)
    optiuni = {
        "vizibilitate": vizibilitate,
        "fara_comentarii": fara_comentarii,
        "fara_duet": fara_duet,
        "fara_stitch": fara_stitch,
    }
    try:
        consimtamant.inregistreaza(
            db,
            lv.id,
            optiuni=optiuni,
            creator=ctx["creator"],
            de_acord=de_acord,
            utilizator_id=u.utilizator_id,
        )
    except consimtamant.ConsimtamantRefuzat as exc:
        db.rollback()
        return pagina(
            request,
            u,
            "panou/publicare_tiktok.html",
            tab="meniu",
            status=422,
            eroare=f"Consimțământul nu a fost salvat: {exc}.",
            **ctx,
        )
    return RedirectResponse(f"/publicare/api/tiktok/{lv.id}?salvat=1", status_code=303)
