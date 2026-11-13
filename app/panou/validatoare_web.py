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
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import productie
from app.conturi import DbSession, Permisiune, SesiuneCurenta, csrf_protect, require_permission, require_role
from app.conturi.roluri import ROLURI_AGENTIE, Rol
from app.ids import new_id
from app.operare import audit
from app.panou.sabloane import pagina
from app.validare import banc, calibrare, carantina, exemple
from app.validare import trimite as trimite_validare
from app.validare.modele import VerdictSalvat

router = APIRouter(prefix="/validatoare", tags=["validatoare"])
Proprietar = Annotated[SesiuneCurenta, Depends(require_role(Rol.PROPRIETAR))]
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
PoateEticheta = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.LIVRABIL_APROBA))]

FEREASTRA_IN_CURS = dt.timedelta(minutes=20)  # o rulare „în curs” mai veche de atât nu mai blochează una nouă
MESAJE = {
    "banc": "Bancul a fost pus în coadă (prioritate P3). Scorurile apar aici când se termină.",
    "banc_in_curs": "O rulare a bancului este deja în curs; așteaptă să se termine.",
    "eticheta": "Eticheta a fost salvată.",
    "eliberat": "Livrabilul a ieșit din carantină; decizia ta a fost înregistrată.",
    "respins": "Livrabilul a fost respins definitiv; decizia ta a fost înregistrată.",
    "contestat": "Contestația a fost înregistrată ca exemplu propus pentru setul de aur.",
    "promovat": "Exemplul a intrat în setul de aur (rularea bancului îl include).",
    "exemplu_respins": "Exemplul propus a fost respins.",
    "eticheta_gresit": "Eticheta a fost salvată; verdictul greșit a devenit exemplu propus "
    "pentru setul de aur.",
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


# --- calibrarea judecătorilor (F5.8)
# ----------------------------------------------------------------------------


@router.get("/calibrare")
def ecran_calibrare(
    request: Request, u: Agentie, db: DbSession, mesaj: str = "", eroare: str = ""
) -> Response:
    """Coada de etichetare (clientul curent prin RLS; proprietarul: toți) și acordul pe judecător."""
    return pagina(
        request,
        u,
        "panou/calibrare.html",
        tab="meniu",
        **_ctx(
            coada=calibrare.coada(db),
            statistici=calibrare.statistici(db),
            mesaj=MESAJE.get(mesaj, ""),
            eroare=eroare,
        ),
    )


@router.post("/calibrare/{eticheta_id}/eticheta", dependencies=[Depends(csrf_protect)])
def eticheteaza(
    u: PoateEticheta,
    db: DbSession,
    eticheta_id: uuid.UUID,
    eticheta: Annotated[str, Form(max_length=10)],
    motiv: Annotated[str, Form(max_length=500)] = "",
) -> Response:
    try:
        _, propus = calibrare.eticheteaza(
            db, eticheta_id, eticheta=eticheta, motiv=motiv, utilizator_id=u.utilizator_id
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Verdictul nu există în coadă.") from None
    except calibrare.EtichetaInvalida as exc:
        return RedirectResponse(f"/validatoare/calibrare?eroare={quote(str(exc))}", status_code=303)
    return RedirectResponse(
        "/validatoare/calibrare?mesaj=" + ("eticheta_gresit" if propus else "eticheta"), status_code=303
    )


# --- carantina și contestațiile (F5.10) ---------------------------------------------------------------


def _inapoi(cale: str, *, mesaj: str = "", eroare: str = "") -> RedirectResponse:
    q = f"mesaj={mesaj}" if mesaj else f"eroare={quote(eroare)}"
    return RedirectResponse(f"{cale}?{q}", status_code=303)


@router.get("/carantina")
def ecran_carantina(request: Request, u: Agentie, db: DbSession, mesaj: str = "") -> Response:
    return pagina(
        request,
        u,
        "panou/carantina.html",
        tab="meniu",
        **_ctx(
            intrari=carantina.lista(db),
            statistica=carantina.statistica_contestatii(db),
            mesaj=MESAJE.get(mesaj, ""),
        ),
    )


@router.get("/carantina/{livrabil_id}")
def detaliu_carantina(
    request: Request, u: Agentie, db: DbSession, livrabil_id: uuid.UUID, mesaj: str = "", eroare: str = ""
) -> Response:
    d = carantina.detaliu(db, livrabil_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Livrabilul nu există.")
    return pagina(
        request,
        u,
        "panou/carantina_detaliu.html",
        tab="meniu",
        **_ctx(**d, mesaj=MESAJE.get(mesaj, ""), eroare=eroare),
    )


@router.post("/carantina/{livrabil_id}/elibereaza", dependencies=[Depends(csrf_protect)])
def elibereaza(
    u: PoateEticheta,
    db: DbSession,
    livrabil_id: uuid.UUID,
    spre: Annotated[str, Form(max_length=20)],
    motiv: Annotated[str, Form(max_length=500)] = "",
) -> Response:
    cale = f"/validatoare/carantina/{livrabil_id}"
    try:
        lv = carantina.elibereaza(db, livrabil_id, spre=spre, motiv=motiv, utilizator_id=u.utilizator_id)
    except carantina.DecizieInvalida as exc:
        return _inapoi(cale, eroare=str(exc))
    except productie.LivrabilInexistent:
        raise HTTPException(status_code=404, detail="Livrabilul nu există.") from None
    except (productie.ConflictStare, productie.TranzitieNepermisa) as exc:
        return _inapoi(cale, eroare=str(exc))
    db.commit()  # starea nouă e în bază înainte ca jobul de validare să o citească
    if spre == "validare":
        trimite_validare(lv.tenant_id, livrabil_id, cheie=f"validare:{livrabil_id}:eliberare:{new_id()}")
    return _inapoi(cale, mesaj="eliberat")


@router.post("/carantina/{livrabil_id}/respinge", dependencies=[Depends(csrf_protect)])
def respinge(
    u: PoateEticheta, db: DbSession, livrabil_id: uuid.UUID, motiv: Annotated[str, Form(max_length=500)] = ""
) -> Response:
    cale = f"/validatoare/carantina/{livrabil_id}"
    try:
        carantina.respinge_definitiv(db, livrabil_id, motiv=motiv, utilizator_id=u.utilizator_id)
    except carantina.DecizieInvalida as exc:
        return _inapoi(cale, eroare=str(exc))
    except productie.LivrabilInexistent:
        raise HTTPException(status_code=404, detail="Livrabilul nu există.") from None
    except (productie.ConflictStare, productie.TranzitieNepermisa) as exc:
        return _inapoi(cale, eroare=str(exc))
    return _inapoi(cale, mesaj="respins")


@router.get("/verdicte/{verdict_id}")
def ecran_verdict(
    request: Request, u: Agentie, db: DbSession, verdict_id: uuid.UUID, mesaj: str = "", eroare: str = ""
) -> Response:
    v = db.get(VerdictSalvat, verdict_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Verdictul nu există.")
    return pagina(
        request,
        u,
        "panou/verdict.html",
        tab="meniu",
        **_ctx(
            verdict=v,
            contestat=verdict_id in carantina.contestate(db, v.livrabil_id),
            mesaj=MESAJE.get(mesaj, ""),
            eroare=eroare,
        ),
    )


@router.post("/verdicte/{verdict_id}/contesta", dependencies=[Depends(csrf_protect)])
def contesta(
    u: PoateEticheta, db: DbSession, verdict_id: uuid.UUID, motiv: Annotated[str, Form(max_length=500)] = ""
) -> Response:
    cale = f"/validatoare/verdicte/{verdict_id}"
    try:
        carantina.contesta(db, verdict_id, motiv=motiv, utilizator_id=u.utilizator_id)
    except carantina.DecizieInvalida as exc:
        return _inapoi(cale, eroare=str(exc))
    except LookupError:
        raise HTTPException(status_code=404, detail="Verdictul nu există.") from None
    return _inapoi(cale, mesaj="contestat")


@router.get("/exemple")
def ecran_exemple(
    request: Request, u: Proprietar, db: DbSession, mesaj: str = "", eroare: str = ""
) -> Response:
    return pagina(
        request,
        u,
        "panou/exemple.html",
        tab="meniu",
        **_ctx(
            propuse=exemple.listeaza(db),
            promovate=exemple.listeaza(db, stare="promovat", limita=50),
            contexte=sorted(banc.seturi.citeste_contexte()[1]),
            mesaj=MESAJE.get(mesaj, ""),
            eroare=eroare,
        ),
    )


@router.post("/exemple/{exemplu_id}/promoveaza", dependencies=[Depends(csrf_protect)])
def promoveaza(
    u: Proprietar,
    db: DbSession,
    exemplu_id: uuid.UUID,
    context_profil: Annotated[str, Form(max_length=40)] = "gol",
    asteptat: Annotated[str, Form(max_length=10)] = "",
    severitate: Annotated[str, Form(max_length=10)] = "",
    text: Annotated[str, Form(max_length=20000)] = "",
    motiv: Annotated[str, Form(max_length=500)] = "",
) -> Response:
    try:
        exemple.promoveaza(
            db,
            exemplu_id,
            utilizator_id=u.utilizator_id,
            context_profil=context_profil,
            text=text or None,
            asteptat=asteptat or None,
            severitate=severitate or None,
            motiv=motiv,
        )
    except exemple.ExempluInvalid as exc:
        return _inapoi("/validatoare/exemple", eroare=str(exc))
    except LookupError:
        raise HTTPException(status_code=404, detail="Exemplul nu există.") from None
    return _inapoi("/validatoare/exemple", mesaj="promovat")


@router.post("/exemple/{exemplu_id}/respinge", dependencies=[Depends(csrf_protect)])
def respinge_exemplu(
    u: Proprietar, db: DbSession, exemplu_id: uuid.UUID, motiv: Annotated[str, Form(max_length=500)] = ""
) -> Response:
    try:
        exemple.respinge(db, exemplu_id, utilizator_id=u.utilizator_id, motiv=motiv)
    except exemple.ExempluInvalid as exc:
        return _inapoi("/validatoare/exemple", eroare=str(exc))
    except LookupError:
        raise HTTPException(status_code=404, detail="Exemplul nu există.") from None
    return _inapoi("/validatoare/exemple", mesaj="exemplu_respins")
