"""Ecranul „CRM” (docs/18, ecranul 16, partea de CRM; F12.1): lead-urile pe etape, fișa unui lead (contact,
sursă și temei, istoricul consimțământului, activități, sarcini), adăugarea unei recomandări, exportul.

Datele sunt ale agenției și se văd doar cu scop de agenție, deci ecranul e al proprietarului. Regulile
(tranzițiile între etape, motivul la „pierdut”, un singur lead deschis pe contact) sunt în `app.crm.registru`.
"""

import csv
import datetime as dt
import io
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.conturi import DbSession, Rol, SesiuneCurenta, csrf_protect, require_role
from app.crm import CrmRefuzat, calificare, inbox, oferte, registru
from app.crm import email as crm_email
from app.panou.sabloane import pagina

router = APIRouter(prefix="/crm", tags=["crm"])
Proprietar = Annotated[SesiuneCurenta, Depends(require_role(Rol.PROPRIETAR))]
MESAJE = {
    "adaugat": "Lead-ul a fost adăugat.",
    "existent": "Contactul avea deja un lead deschis: l-am deschis pe acela, fără să-l dublez.",
    "etapa": "Etapa a fost schimbată.",
    "nota": "Nota a fost salvată.",
    "sarcina": "Sarcina a fost adăugată.",
    "facuta": "Sarcina a fost închisă.",
    "retras": "Consimțământul a fost retras.",
    "suprimat": "Adresa a fost pusă în lista de suprimare.",
    "regula": "Regula a fost salvată.",
    "oferta": "Oferta a fost pregătită și așteaptă aprobarea ta.",
    "aprobata": "Oferta a fost aprobată și trimisă.",
    "respinsa": "Oferta a fost respinsă.",
    "canal": "Canalul a fost aprobat: mesajele lui se citesc de acum.",
    "canal_oprit": "Canalul nu se mai citește.",
}


def _id(text: str) -> uuid.UUID:
    try:
        return uuid.UUID(text)
    except ValueError:
        raise HTTPException(status_code=404, detail="Lead inexistent.") from None


def _etichete() -> dict[str, Any]:
    return {
        "etichete_etapa": registru.ETICHETE_ETAPA,
        "etichete_sursa": registru.ETICHETE_SURSA,
        "etichete_temei": registru.ETICHETE_TEMEI,
    }


def _lista(
    request: Request, u: SesiuneCurenta, db: Any, *, etapa: str = "", status: int = 200, eroare: str = ""
) -> Response:
    if etapa and etapa not in registru.ETAPE:
        raise HTTPException(status_code=404, detail="Etapă necunoscută.")
    return pagina(
        request,
        u,
        "panou/crm.html",
        tab="meniu",
        status=status,
        randuri=registru.lista(db, etapa or None),
        numar=registru.numar_pe_etape(db),
        sarcini=registru.sarcini_deschise(db),
        etapa=etapa,
        azi=dt.datetime.now(dt.UTC).date(),
        mesaj=MESAJE.get(request.query_params.get("mesaj", ""), ""),
        eroare=eroare,
        **_etichete(),
    )


def _fisa(
    request: Request, u: SesiuneCurenta, db: Any, lead_id: uuid.UUID, *, status: int = 200, eroare: str = ""
) -> Response:
    f = registru.fisa(db, lead_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Lead inexistent.")
    return pagina(
        request,
        u,
        "panou/crm_lead.html",
        tab="meniu",
        status=status,
        mesaj=MESAJE.get(request.query_params.get("mesaj", ""), ""),
        eroare=eroare,
        maine=(dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).date().isoformat(),
        calificare=calificare.curenta(db, lead_id),
        etichete_grupa=calificare.ETICHETE_GRUPA,
        **f,
        **_etichete(),
    )


def _eroare(exc: Exception) -> str:
    return str(exc).capitalize() + "."


@router.get("")
def lista(request: Request, u: Proprietar, db: DbSession, etapa: str = "") -> Response:
    return _lista(request, u, db, etapa=etapa)


@router.get("/export.csv")
def export(u: Proprietar, db: DbSession) -> Response:
    tampon = io.StringIO()
    csv.writer(tampon).writerows(registru.export(db))
    return Response(
        tampon.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="crm.csv"', "Cache-Control": "no-store"},
    )


def _email(request: Request, u: SesiuneCurenta, db: Any, *, status: int = 200, eroare: str = "") -> Response:
    return pagina(
        request,
        u,
        "panou/crm_email.html",
        tab="meniu",
        status=status,
        stare=crm_email.stare(db),
        matrice=crm_email.matrice(db),
        prag_respingeri=crm_email.PRAG_RESPINGERI * 100,
        prag_plangeri=crm_email.PRAG_PLANGERI * 100,
        mesaj=MESAJE.get(request.query_params.get("mesaj", ""), ""),
        eroare=eroare,
    )


@router.get("/email")
def email(request: Request, u: Proprietar, db: DbSession) -> Response:
    return _email(request, u, db)


@router.post("/email/suprimare", dependencies=[Depends(csrf_protect)])
async def suprima(request: Request, u: Proprietar, db: DbSession) -> Response:
    f = await request.form()
    motiv = str(f.get("motiv") or "manual")
    try:
        crm_email.suprima(db, str(f.get("email") or ""), motiv, sursa="adăugată din panou")
    except CrmRefuzat as exc:
        return _email(request, u, db, status=422, eroare=_eroare(exc))
    return RedirectResponse("/crm/email?mesaj=suprimat", status_code=303)


@router.post("/email/regula", dependencies=[Depends(csrf_protect)])
async def regula(request: Request, u: Proprietar, db: DbSession) -> Response:
    f = await request.form()
    try:
        crm_email.seteaza_regula(
            db,
            tara=str(f.get("tara") or ""),
            tip_destinatar=str(f.get("tip_destinatar") or ""),
            regula=str(f.get("regula") or ""),
            mentiuni=str(f.get("mentiuni") or ""),
            verificat_de=str(f.get("verificat_de") or ""),
            utilizator_id=u.utilizator_id,
        )
    except CrmRefuzat as exc:
        return _email(request, u, db, status=422, eroare=_eroare(exc))
    return RedirectResponse("/crm/email?mesaj=regula", status_code=303)


@router.post("/lead", dependencies=[Depends(csrf_protect)])
async def adauga(request: Request, u: Proprietar, db: DbSession) -> Response:
    f = await request.form()
    try:
        lead, nou = registru.primeste(
            db,
            email=str(f.get("email") or ""),
            firma=str(f.get("firma") or ""),
            site_url=str(f.get("site_url") or ""),
            nume=str(f.get("nume") or ""),
            telefon=str(f.get("telefon") or ""),
            sursa="recomandare",
            dovada=str(f.get("dovada") or ""),
            utilizator_id=u.utilizator_id,
        )
    except CrmRefuzat as exc:
        return _lista(request, u, db, status=422, eroare=_eroare(exc))
    return RedirectResponse(f"/crm/lead/{lead.id}?mesaj={'adaugat' if nou else 'existent'}", status_code=303)


@router.get("/lead/{lead_id}")
def fisa(request: Request, lead_id: str, u: Proprietar, db: DbSession) -> Response:
    return _fisa(request, u, db, _id(lead_id))


@router.post("/lead/{lead_id}/{actiune}", dependencies=[Depends(csrf_protect)])
async def schimba(request: Request, lead_id: str, actiune: str, u: Proprietar, db: DbSession) -> Response:
    lid = _id(lead_id)
    f = await request.form()
    try:
        if actiune == "etapa":
            registru.muta_etapa(
                db,
                lid,
                str(f.get("etapa") or ""),
                utilizator_id=u.utilizator_id,
                motiv=str(f.get("motiv") or ""),
            )
        elif actiune == "nota":
            registru.adauga_nota(db, lid, str(f.get("nota") or ""), utilizator_id=u.utilizator_id)
        elif actiune == "sarcina":
            try:
                scadenta = dt.date.fromisoformat(str(f.get("scadenta") or ""))
            except ValueError:
                raise CrmRefuzat("data scadenței nu e validă") from None
            if registru.fisa(db, lid) is None:
                raise HTTPException(status_code=404, detail="Lead inexistent.")
            registru.creeaza_sarcina(db, lid, str(f.get("titlu") or ""), scadenta)
        elif actiune == "oferta":
            oferte.genereaza(db, lid)
        elif actiune == "retrage":
            date = registru.fisa(db, lid)
            if date is None:
                raise HTTPException(status_code=404, detail="Lead inexistent.")
            registru.noteaza_consimtamant(
                db,
                date["contact"].id,
                str(f.get("scop") or ""),
                acordat=False,
                sursa="panou",
                temei="retragere_la_cerere",
                dovada=str(f.get("dovada") or ""),
            )
            actiune = "retras"
        else:
            raise HTTPException(status_code=404, detail="Acțiune necunoscută.")
    except CrmRefuzat as exc:
        if registru.fisa(db, lid) is None:
            raise HTTPException(status_code=404, detail="Lead inexistent.") from None
        return _fisa(request, u, db, lid, status=422, eroare=_eroare(exc))
    return RedirectResponse(f"/crm/lead/{lid}?mesaj={actiune}", status_code=303)


@router.post("/sarcina/{sarcina_id}/inchide", dependencies=[Depends(csrf_protect)])
def inchide_sarcina(request: Request, sarcina_id: str, u: Proprietar, db: DbSession) -> Response:
    try:
        registru.inchide_sarcina(db, _id(sarcina_id))
    except CrmRefuzat as exc:
        return _lista(request, u, db, status=422, eroare=_eroare(exc))
    return RedirectResponse("/crm?mesaj=facuta", status_code=303)


# --- ofertele de aprobat (F12.6) ----------------------------------------------------------------------------
def _oferte(request: Request, u: SesiuneCurenta, db: Any, *, status: int = 200, eroare: str = "") -> Response:
    return pagina(
        request,
        u,
        "panou/crm_oferte.html",
        tab="meniu",
        status=status,
        oferte=oferte.de_aprobat(db),
        text_oferta=oferte.text_oferta,
        etichete_stare=oferte.ETICHETE_STARE,
        mesaj=MESAJE.get(request.query_params.get("mesaj", ""), ""),
        eroare=eroare,
    )


@router.get("/oferte")
def lista_oferte(request: Request, u: Proprietar, db: DbSession) -> Response:
    return _oferte(request, u, db)


@router.post("/oferte/{oferta_id}/{decizie}", dependencies=[Depends(csrf_protect)])
async def decide_oferta(
    request: Request, oferta_id: str, decizie: str, u: Proprietar, db: DbSession
) -> Response:
    oid = _id(oferta_id)
    f = await request.form()
    try:
        if decizie == "aproba":
            oferte.aproba(db, oid, utilizator_id=u.utilizator_id)
            mesaj = "aprobata"
        elif decizie == "respinge":
            oferte.respinge(db, oid, utilizator_id=u.utilizator_id, motiv=str(f.get("motiv") or ""))
            mesaj = "respinsa"
        else:
            raise HTTPException(status_code=404, detail="Decizie necunoscută.")
    except CrmRefuzat as exc:
        return _oferte(request, u, db, status=422, eroare=_eroare(exc))
    return RedirectResponse(f"/crm/oferte?mesaj={mesaj}", status_code=303)


# --- inboxul social (F12.7) ---------------------------------------------------------------------------------
def _inbox(request: Request, u: SesiuneCurenta, db: Any, *, status: int = 200, eroare: str = "") -> Response:
    clasa = request.query_params.get("clasa", "")
    if clasa and clasa not in inbox.CLASE:
        raise HTTPException(status_code=404, detail="Clasă necunoscută.")
    return pagina(
        request,
        u,
        "panou/crm_inbox.html",
        tab="meniu",
        status=status,
        canale=inbox.canale(db),
        canale_posibile=inbox.canale_posibile(),
        mesaje=inbox.mesaje(db, clasa=clasa),
        clasa=clasa,
        etichete_clasa=inbox.ETICHETE_CLASA,
        mesaj=MESAJE.get(request.query_params.get("mesaj", ""), ""),
        eroare=eroare,
    )


@router.get("/inbox")
def lista_inbox(request: Request, u: Proprietar, db: DbSession) -> Response:
    return _inbox(request, u, db)


@router.post("/inbox/canal", dependencies=[Depends(csrf_protect)])
async def canal_inbox(request: Request, u: Proprietar, db: DbSession) -> Response:
    f = await request.form()
    canal, actiune = str(f.get("canal") or ""), str(f.get("actiune") or "aproba")
    try:
        if actiune == "opreste":
            inbox.opreste_canal(db, canal, utilizator_id=u.utilizator_id)
        else:
            inbox.aproba_canal(db, canal, utilizator_id=u.utilizator_id)
    except CrmRefuzat as exc:
        return _inbox(request, u, db, status=422, eroare=_eroare(exc))
    return RedirectResponse(
        f"/crm/inbox?mesaj={'canal_oprit' if actiune == 'opreste' else 'canal'}", status_code=303
    )
