"""Ecranul „Validatoare” (18.2, ecranul 10): bancul de evaluare (F5.7, K4).

- Bancul: ultima rulare terminată (poarta F5, scorurile pe validator, matricele de confuzie, exemplele
greșite), istoricul
  rulărilor și butonul care pornește bancul ca job durabil (P3, coada `invatare`).

Doar proprietarul (singurul rol cu scop de agenție: rulările bancului sunt la nivelul platformei). Pornirea
cere CSRF și lasă
urmă în jurnalul de audit. Seturile de aur nu se pot modifica de aici: sunt fișiere în depozit, schimbate doar
printr-un commit.
"""

import datetime as dt
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.conturi import DbSession, SesiuneCurenta, csrf_protect, require_role
from app.conturi.roluri import Rol
from app.operare import audit
from app.panou.sabloane import pagina
from app.validare import banc

router = APIRouter(prefix="/validatoare", tags=["validatoare"])
Proprietar = Annotated[SesiuneCurenta, Depends(require_role(Rol.PROPRIETAR))]

FEREASTRA_IN_CURS = dt.timedelta(minutes=20)  # o rulare „în curs” mai veche de atât nu mai blochează una nouă
MESAJE = {
    "banc": "Bancul a fost pus în coadă (prioritate P3). Scorurile apar aici când se termină.",
    "banc_in_curs": "O rulare a bancului este deja în curs; așteaptă să se termine.",
}
NUME_VALIDATORI = {
    "G1": "Structură",
    "G2": "Fapte",
    "G3": "Politici",
    "G4": "Ton",
    "G7": "Originalitate",
    "G8": "Lizibilitate și conversie",
    "G9": "Juridic",
    "G10": "Limbă",
}


def procent(x: float | None) -> str:
    return "–" if x is None else f"{x * 100:.1f}%".replace(".", ",")


def _ctx(**extra: Any) -> dict[str, Any]:
    return {"procent": procent, "nume_validatori": NUME_VALIDATORI, **extra}


@router.get("")
def ecran(request: Request, u: Proprietar, db: DbSession, mesaj: str = "") -> Response:
    ultima = banc.depozit.ultima_terminata(db)
    return pagina(
        request,
        u,
        "panou/validatoare.html",
        tab="meniu",
        **_ctx(
            ultima=ultima,
            scoruri=ultima.scoruri if ultima else None,
            rulari=banc.depozit.recente(db, 10),
            mesaj=MESAJE.get(mesaj, ""),
        ),
    )


@router.get("/banc/{rulare_id}")
def detaliu_banc(request: Request, u: Proprietar, db: DbSession, rulare_id: uuid.UUID) -> Response:
    r = banc.depozit.citeste(db, rulare_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Rularea nu există.")
    return pagina(request, u, "panou/validatoare_banc.html", tab="meniu", **_ctx(rulare=r, scoruri=r.scoruri))


@router.post("/banc/porneste", dependencies=[Depends(csrf_protect)])
def porneste_banc(u: Proprietar, db: DbSession) -> Response:
    acum = dt.datetime.now(dt.UTC)
    if banc.depozit.in_curs(db, de_la=acum - FEREASTRA_IN_CURS) is not None:
        return RedirectResponse("/validatoare?mesaj=banc_in_curs", status_code=303)
    rulare = banc.depozit.porneste(db, utilizator_id=u.utilizator_id)
    audit.record(
        db,
        "validare.banc_pornit",
        obiect_tip="banc_rulare",
        obiect_id=rulare.id,
        utilizator_id=u.utilizator_id,
        tenant_id=None,
        detalii={"amprenta_seturi": banc.seturi.amprenta_seturi()},
    )
    db.commit()  # rularea există în bază înainte ca jobul să o caute
    banc.fluxuri.trimite(rulare.id)
    return RedirectResponse("/validatoare?mesaj=banc", status_code=303)
