"""Ecranul „Publicare asistată” (F6.6, docs/15 §15.2, docs/18): pachetele gata de publicat, întâi pentru
telefon.

Pe fiecare card: canalul, ora recomandată, textul final, pașii obligatorii (eticheta AI) și butonul
„Partajează” (meniul
de partajare al telefonului, `navigator.share`; altfel textul se copiază). După publicare, omul lipește linkul
postării:
livrabilul devine „Publicat” și linkul apare în sistem. CSRF; permisiunea `livrabil.aproba`; auditul îl scrie
serviciul.
"""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import publicare
from app.conturi import (
    DbSession,
    Permisiune,
    SesiuneCurenta,
    csrf_protect,
    lista_clienti,
    require_permission,
    require_role,
)
from app.conturi.roluri import ROLURI_AGENTIE
from app.panou.sabloane import pagina

router = APIRouter(prefix="/publicare", tags=["publicare"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
PoatePublica = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.LIVRABIL_APROBA))]
MESAJE = {"publicat": "Linkul a fost salvat: postarea apare ca publicată, iar măsurarea poate porni."}


def _pagina(
    request: Request, u: SesiuneCurenta, db: DbSession, *, status: int = 200, **extra: object
) -> Response:
    clienti = {c.id: c.nume for c in lista_clienti(db)}
    return pagina(
        request,
        u,
        "panou/publicare.html",
        tab="meniu",
        status=status,
        pregatite=[
            (
                p,
                dt.datetime.fromisoformat(p.pachet["ora_recomandata"])
                if p.pachet.get("ora_recomandata")
                else None,
            )
            for p in publicare.asistata.pregatite(db)
        ],
        publicate=publicare.asistata.publicate(db),
        clienti=clienti,
        **extra,
    )


@router.get("")
def lista(request: Request, u: Agentie, db: DbSession, mesaj: str = "") -> Response:
    return _pagina(request, u, db, mesaj=MESAJE.get(mesaj, ""))


@router.post("/{publicare_id}/link", dependencies=[Depends(csrf_protect)])
def link(
    request: Request,
    u: PoatePublica,
    db: DbSession,
    publicare_id: str,
    link: Annotated[str, Form(max_length=600)] = "",
) -> Response:
    try:
        pid = uuid.UUID(publicare_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Nu există.") from None
    try:
        publicare.asistata.confirma(db, pid, link=link, utilizator_id=u.utilizator_id)
    except publicare.asistata.EroarePublicare as exc:
        db.rollback()
        return _pagina(request, u, db, status=422, eroare=f"Linkul nu a fost salvat: {exc}.")
    return RedirectResponse("/publicare?mesaj=publicat", status_code=303)
