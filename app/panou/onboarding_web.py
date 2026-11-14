"""Ecranul de onboarding (F4.4): operatorul completează interviul pentru client, vede brieful compus și
îl trimite
spre aprobare. Portalul clientului (F7) va folosi aceleași funcții din `app.onboarding.sesiuni`.

Întâi pentru telefon: o întrebare pe ecran, câmpuri mari, fără tabele. CSRF pe orice schimbare, permisiunea
`onboarding.completeaza`, audit scris de serviciu. Brieful cu câmpuri goale nu se poate trimite (poarta
din Creier).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import creier, onboarding, portal
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
from app.onboarding import brief, ghid, interviu, sesiuni
from app.panou.sabloane import pagina

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
PoateCompleta = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.ONBOARDING_COMPLETEAZA))]

MESAJE = {
    "pornit": "Interviul a fost pornit. Răspunde la prima întrebare.",
    "raspuns": "Răspunsul a fost salvat.",
    "compune": "Brieful se compune din răspunsuri și materiale. Reîncarcă pagina peste câteva secunde.",
    "camp": "Câmpul a fost actualizat.",
    "trimis": "Brieful a fost trimis spre aprobare în Creierul de brand.",
    "ton_pornit": "Variantele de ton se pregătesc. Reîncarcă pagina peste câteva secunde.",
    "ghid_propus": "Ghidul de brand a fost propus. Îl aprobi în Creierul de brand.",
    "invitat": "Invitația a fost trimisă: clientul își activează contul din email și continuă în portal.",
}


def _id(valoare: str) -> uuid.UUID:
    try:
        return uuid.UUID(valoare)
    except ValueError:
        raise HTTPException(status_code=404, detail="Clientul nu există.") from None


def _client(db: DbSession, client_id: str):  # type: ignore[no-untyped-def]
    cid = _id(client_id)
    for c in lista_clienti(db):
        if c.id == cid:
            return c
    raise HTTPException(status_code=404, detail="Clientul nu există.")


def _pagina(
    request: Request, u: SesiuneCurenta, db: DbSession, client_id: str, *, status: int = 200, **extra: object
) -> Response:
    c = _client(db, client_id)
    s = sesiuni.sesiune_deschisa(db, c.id)
    ultima_trimisa = None
    if s is None:
        ultima_trimisa = creier.gaseste_intrare(
            db,
            tenant_id=c.id,
            compartiment=creier.Compartiment.BRIEF,
            cheie=onboarding.completare.CHEIE_BRIEF,
        )
    date: dict[str, object] = {"client": c, "s": s, "ultima_trimisa": ultima_trimisa}
    if s is not None:
        rows = sesiuni.intrebari(db, s.id)
        date.update(
            progres=sesiuni.progres(db, s.id),
            urmatoarea=sesiuni.urmatoarea(db, s.id),
            raspunse=[r for r in rows if r.raspuns is not None],
            sectiune=None,
            campuri=brief.CAMPURI,
            brief=s.brief or {},
            probleme=list(s.brief_probleme or []),
        )
        urm = date["urmatoarea"]
        if urm is not None:
            date["sectiune"] = interviu.sectiune_intrebare(urm.cod).titlu  # type: ignore[attr-defined]
            date["ajutor"] = interviu.camp_intrebare(urm.cod).ajutor  # type: ignore[attr-defined]
    return pagina(
        request, u, "panou/onboarding.html", tab="meniu", status=status,
        poate_completa=poate(u.rol, Permisiune.ONBOARDING_COMPLETEAZA), **date, **extra,
    )  # fmt: skip


@router.get("")
def index(request: Request, u: Agentie, db: DbSession) -> Response:
    clienti = lista_clienti(db)
    stari = {c.id: sesiuni.sesiune_deschisa(db, c.id) for c in clienti}
    return pagina(request, u, "panou/onboarding_lista.html", tab="meniu", clienti=clienti, stari=stari)


@router.get("/{client_id}")
def vezi(request: Request, u: Agentie, db: DbSession, client_id: str, mesaj: str = "") -> Response:
    return _pagina(request, u, db, client_id, mesaj=MESAJE.get(mesaj, ""))


@router.post("/{client_id}/invita", dependencies=[Depends(csrf_protect)])
def invita(
    request: Request,
    u: PoateCompleta,
    db: DbSession,
    client_id: str,
    email: Annotated[str, Form(max_length=254)],
) -> Response:
    """Linkul de activare a portalului pentru client (F7.3), pe email."""
    c = _client(db, client_id)
    try:
        portal.cont.invita(db, c.id, email, creat_de=u.utilizator_id, motiv=f"manual:{uuid.uuid4().hex[:8]}")
    except (portal.cont.InvitatieInvalida, ValueError) as exc:
        db.rollback()
        return _pagina(request, u, db, client_id, status=422, eroare=str(exc))
    return RedirectResponse(f"/onboarding/{c.id}?mesaj=invitat", status_code=303)


@router.post("/{client_id}/porneste", dependencies=[Depends(csrf_protect)])
def porneste(request: Request, u: PoateCompleta, db: DbSession, client_id: str) -> Response:
    c = _client(db, client_id)
    sesiuni.deschide(db, tenant_id=c.id, utilizator_id=u.utilizator_id)
    return RedirectResponse(f"/onboarding/{c.id}?mesaj=pornit", status_code=303)


@router.post("/{client_id}/raspunde", dependencies=[Depends(csrf_protect)])
def raspunde(
    request: Request,
    u: PoateCompleta,
    db: DbSession,
    client_id: str,
    intrebare_id: Annotated[str, Form()],
    raspuns: Annotated[str, Form(max_length=6000)],
) -> Response:
    c = _client(db, client_id)
    s = sesiuni.sesiune_deschisa(db, c.id)
    if s is None:
        raise HTTPException(status_code=404, detail="Nu există un interviu deschis.")
    try:
        sesiuni.raspunde(db, s.id, _id(intrebare_id), raspuns, utilizator_id=u.utilizator_id)
    except onboarding.EroareOnboarding as exc:
        return _pagina(request, u, db, client_id, status=422, eroare=str(exc))
    return RedirectResponse(f"/onboarding/{c.id}?mesaj=raspuns", status_code=303)


@router.post("/{client_id}/compune", dependencies=[Depends(csrf_protect)])
def compune(request: Request, u: PoateCompleta, db: DbSession, client_id: str) -> Response:
    c = _client(db, client_id)
    s = sesiuni.sesiune_deschisa(db, c.id)
    if s is None:
        raise HTTPException(status_code=404, detail="Nu există un interviu deschis.")
    if not sesiuni.progres(db, s.id).terminat:
        return _pagina(request, u, db, client_id, status=409, eroare="Interviul nu e terminat.")
    sesiuni_id, tenant = s.id, c.id
    db.commit()  # fluxul citește sesiunea din altă conexiune
    onboarding.fluxuri.trimite_compunerea(
        tenant, sesiuni_id, u.utilizator_id, cheie=f"brief:{sesiuni_id}:{uuid.uuid4().hex[:8]}"
    )
    return RedirectResponse(f"/onboarding/{c.id}?mesaj=compune", status_code=303)


@router.post("/{client_id}/camp", dependencies=[Depends(csrf_protect)])
def camp(
    request: Request,
    u: PoateCompleta,
    db: DbSession,
    client_id: str,
    camp: Annotated[str, Form()],
    valoare: Annotated[str, Form(max_length=2500)],
) -> Response:
    c = _client(db, client_id)
    s = sesiuni.sesiune_deschisa(db, c.id)
    if s is None:
        raise HTTPException(status_code=404, detail="Nu există un interviu deschis.")
    try:
        onboarding.completare.seteaza_camp(db, s.id, camp, valoare, utilizator_id=u.utilizator_id)
    except onboarding.EroareOnboarding as exc:
        return _pagina(request, u, db, client_id, status=409, eroare=str(exc))
    return RedirectResponse(f"/onboarding/{c.id}?mesaj=camp", status_code=303)


@router.post("/{client_id}/trimite", dependencies=[Depends(csrf_protect)])
def trimite(request: Request, u: PoateCompleta, db: DbSession, client_id: str) -> Response:
    c = _client(db, client_id)
    s = sesiuni.sesiune_deschisa(db, c.id)
    if s is None:
        raise HTTPException(status_code=404, detail="Nu există un interviu deschis.")
    try:
        onboarding.completare.trimite_spre_aprobare(db, s.id, utilizator_id=u.utilizator_id)
    except creier.PoartaInchisa as exc:
        return _pagina(
            request, u, db, client_id, status=422,
            eroare="Brieful are câmpuri necompletate și nu poate fi trimis: " + "; ".join(exc.probleme[:6]),
        )  # fmt: skip
    except onboarding.EroareOnboarding as exc:
        return _pagina(request, u, db, client_id, status=409, eroare=str(exc))
    return RedirectResponse(f"/onboarding/{c.id}?mesaj=trimis", status_code=303)


# --- ghidul de brand (F4.5)


def _pagina_ghid(
    request: Request, u: SesiuneCurenta, db: DbSession, client_id: str, *, status: int = 200, **extra: object
) -> Response:
    c = _client(db, client_id)
    brief_ok = True
    try:
        onboarding.completare.brief_aprobat(db, c.id)
    except creier.RegulaCreier:
        brief_ok = False
    intrare = creier.gaseste_intrare(
        db, tenant_id=c.id, compartiment=creier.Compartiment.PROFIL_BRAND, cheie=ghid.CHEIE_GHID
    )
    return pagina(
        request, u, "panou/onboarding_ghid.html", tab="meniu", status=status, client=c,
        variante=ghid.variante(db, c.id), brief_ok=brief_ok, intrare=intrare, parti=ghid.PARTI,
        poate_completa=poate(u.rol, Permisiune.ONBOARDING_COMPLETEAZA), **extra,
    )  # fmt: skip


@router.get("/{client_id}/ghid")
def ghid_vezi(request: Request, u: Agentie, db: DbSession, client_id: str, mesaj: str = "") -> Response:
    return _pagina_ghid(request, u, db, client_id, mesaj=MESAJE.get(mesaj, ""))


@router.post("/{client_id}/ghid/propune", dependencies=[Depends(csrf_protect)])
def ghid_propune(request: Request, u: PoateCompleta, db: DbSession, client_id: str) -> Response:
    c = _client(db, client_id)
    try:
        onboarding.completare.brief_aprobat(db, c.id)
    except creier.RegulaCreier as exc:
        return _pagina_ghid(request, u, db, client_id, status=409, eroare=str(exc))
    tenant = c.id
    db.commit()
    onboarding.fluxuri.trimite_propunerea_de_ton(
        tenant, u.utilizator_id, cheie=f"ton:{tenant}:{uuid.uuid4().hex[:8]}"
    )
    return RedirectResponse(f"/onboarding/{c.id}/ghid?mesaj=ton_pornit", status_code=303)


@router.post("/{client_id}/ghid/alege", dependencies=[Depends(csrf_protect)])
async def ghid_alege(request: Request, u: PoateCompleta, db: DbSession, client_id: str) -> Response:
    c = _client(db, client_id)
    form = await request.form()
    try:
        if form.get("varianta"):
            ghid.alege(db, c.id, utilizator_id=u.utilizator_id, varianta=int(str(form["varianta"])))
        else:
            ghid.alege(
                db, c.id, utilizator_id=u.utilizator_id,
                combina={p: int(str(form.get(f"parte_{p}", ""))) for p in ghid.PARTI},
            )  # fmt: skip
    except (ValueError, creier.RegulaCreier, ghid.VariantaInvalida) as exc:
        db.rollback()
        return _pagina_ghid(request, u, db, client_id, status=422, eroare=f"Nu s-a putut salva ghidul: {exc}")
    return RedirectResponse(f"/onboarding/{c.id}/ghid?mesaj=ghid_propus", status_code=303)
