"""Punctul minim din panou pentru faptele Creierului (F4.6): lista propunerilor, „Aprobă” și
„Respinge”.

Ecranul bogat „Creierul de brand” (editare, versiuni, profil) este F4.8. Aici: faptele cu o
versiune propusă (extrase din materiale sau introduse de un om), fiecare cu sursa și citatul
exact, și cele două acțiuni, cu CSRF, permisiunea `creier.editeaza` și audit (scris de serviciu,
în aceeași tranzacție). Doar un fapt aprobat de un om ajunge în context.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import creier
from app.conturi import (
    DbSession,
    Permisiune,
    SesiuneCurenta,
    csrf_protect,
    lista_clienti,
    poate,
    require_permission,
    require_role,
)
from app.conturi.roluri import ROLURI_AGENTIE
from app.creier import fapte
from app.panou.sabloane import pagina

router = APIRouter(prefix="/creier/fapte", tags=["creier"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
PoateEdita = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.CREIER_EDITEAZA))]
MOTIV_MAXIM = 300

MESAJE = {
    "aprobat": "Faptul a fost aprobat. De acum poate intra în context.",
    "respins": "Faptul a fost respins, cu motivul tău.",
}


def _id(valoare: str) -> uuid.UUID:
    try:
        return uuid.UUID(valoare)
    except ValueError:
        raise HTTPException(status_code=404, detail="Faptul nu există.") from None


def _valoare(f: fapte.FaptPropus) -> str:
    v = f.valoare or {}
    if v.get("numar") is None and not v.get("text"):
        return ""
    parti = [str(v["numar"])] if v.get("numar") is not None else []
    parti += [p for p in (v.get("moneda"), v.get("unitate"), v.get("text")) if p]
    return " ".join(parti)


def _eticheta_tip(tip: str) -> str:
    try:
        return fapte.ETICHETE_TIP[fapte.TipFapt(tip)]
    except (ValueError, KeyError):
        return tip


def _pagina(
    request: Request,
    u: SesiuneCurenta,
    db: DbSession,
    *,
    status: int = 200,
    client: str = "",
    **extra: object,
) -> Response:
    clienti = lista_clienti(db)
    nume_client = {c.id: c.nume for c in clienti}
    filtru = _id(client) if client else None
    randuri = [
        {
            "f": f,
            "client": nume_client.get(f.tenant_id, "–"),
            "valoare": _valoare(f),
            "tip": _eticheta_tip(f.tip),
        }
        for f in fapte.propuneri(db, tenant_id=filtru)
    ]
    return pagina(
        request, u, "panou/creier_fapte.html", tab="meniu", status=status, randuri=randuri, clienti=clienti,
        client_ales=client, poate_edita=poate(u.rol, Permisiune.CREIER_EDITEAZA), **extra,
    )  # fmt: skip


@router.get("")
def lista(request: Request, u: Agentie, db: DbSession, client: str = "", mesaj: str = "") -> Response:
    return _pagina(request, u, db, client=client, mesaj=MESAJE.get(mesaj, ""))


@router.post("/{intrare_id}/aproba", dependencies=[Depends(csrf_protect)])
def aproba(
    request: Request, u: PoateEdita, db: DbSession, intrare_id: str, versiune: Annotated[int, Form(ge=1)]
) -> Response:
    try:
        fapte.aproba_fapt(db, _id(intrare_id), versiune, utilizator_id=u.utilizator_id)
    except creier.IntrareInexistenta:
        raise HTTPException(status_code=404, detail="Faptul nu există.") from None
    except creier.TranzitieNepermisa as exc:
        return _pagina(request, u, db, status=409, eroare=str(exc))
    return RedirectResponse("/creier/fapte?mesaj=aprobat", status_code=303)


@router.post("/{intrare_id}/respinge", dependencies=[Depends(csrf_protect)])
def respinge(
    request: Request,
    u: PoateEdita,
    db: DbSession,
    intrare_id: str,
    versiune: Annotated[int, Form(ge=1)],
    motiv: Annotated[str, Form(max_length=MOTIV_MAXIM)] = "",
) -> Response:
    if len(motiv.strip()) < 3:
        return _pagina(
            request, u, db, status=422, eroare="Scrie motivul respingerii (cel puțin 3 caractere)."
        )
    try:
        fapte.respinge_fapt(db, _id(intrare_id), versiune, utilizator_id=u.utilizator_id, motiv=motiv.strip())
    except creier.IntrareInexistenta:
        raise HTTPException(status_code=404, detail="Faptul nu există.") from None
    except creier.TranzitieNepermisa as exc:
        return _pagina(request, u, db, status=409, eroare=str(exc))
    return RedirectResponse("/creier/fapte?mesaj=respins", status_code=303)
