"""Paginile coajei: Acasă, Aprobări, Producție, Alerte, Meniu, notificări, butoanele de oprire, PWA."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from app import __version__
from app.config import get_settings
from app.conturi import (
    DbSession,
    Permisiune,
    SesiuneCurenta,
    cauta_clienti,
    csrf_protect,
    lista_clienti,
    poate,
    require_permission,
    require_role,
)
from app.conturi.roluri import ROLURI_AGENTIE
from app.operare import audit, backup, livrare, notificari, opriri
from app.operare.opriri import Oprire
from app.panou.sabloane import STATIC, pagina

router = APIRouter(tags=["panou"])

# Toate ecranele coajei: utilizator de agenție cu al doilea factor încheiat. Clienții (403) vin în F7.
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
PoateOpri = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.OPRIRE_FOLOSESTE))]

MESAJE = {
    "oprit": "Oprirea a fost înregistrată.",
    "repornit": "Repornirea a fost înregistrată.",
}


# --- PWA (publice: browserul le cere fără sesiune) ---------------------------------------------


@router.get("/manifest.webmanifest", include_in_schema=False)
def manifest() -> FileResponse:
    return FileResponse(
        STATIC / "manifest.webmanifest",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/sw.js", include_in_schema=False)
def service_worker() -> FileResponse:
    """Din rădăcină, ca să controleze tot site-ul. Fără cache, ca actualizările să ajungă repede."""
    return FileResponse(
        STATIC / "sw.js",
        media_type="text/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


# --- ecrane -----------------------------------------------------------------------------------------------


def _stare_sistem(db: DbSession, u: SesiuneCurenta) -> dict[str, Any]:
    try:
        db.execute(text("SELECT 1"))
        baza_ok = True
    except Exception:
        baza_ok = False
    active = opriri.active(db)
    globale_oprite = {o.tip for o in active if o.tip != Oprire.CLIENT.value}
    clienti_opriti = {o.tenant_id for o in active if o.tip == Oprire.CLIENT.value}
    return {
        "versiune": get_settings().version if get_settings().version != "dev" else __version__,
        "mediu": get_settings().env,
        "baza_ok": baza_ok,
        "backup": backup.citeste_stare(),
        "livrare": livrare.citeste_stare(db, istoric=1) if u.rol.value == "proprietar" else None,
        "opriri_active": active,
        "globale": [
            {"tip": t.value, "eticheta": opriri.ETICHETE[t], "oprit": t.value in globale_oprite}
            for t in opriri.GLOBALE
        ],
        "clienti": [
            {"id": str(c.id), "nume": c.nume, "oprit": c.id in clienti_opriti} for c in lista_clienti(db)
        ],
        "poate_opri": poate(u.rol, Permisiune.OPRIRE_FOLOSESTE),
    }


@router.get("/")
def acasa(request: Request, u: Agentie, db: DbSession, mesaj: str = "") -> Response:
    return pagina(
        request, u, "panou/acasa.html", tab="acasa", mesaj=MESAJE.get(mesaj, ""), **_stare_sistem(db, u)
    )


@router.get("/fragment/stare")
def fragment_stare(request: Request, u: Agentie, db: DbSession) -> Response:
    return pagina(request, u, "panou/_stare.html", tab="acasa", **_stare_sistem(db, u))


@router.get("/aprobari")
def aprobari(request: Request, u: Agentie) -> Response:
    return pagina(
        request,
        u,
        "panou/gol.html",
        tab="aprobari",
        titlu="Aprobări",
        pictograma="✓",
        text="Aici vei vedea livrabilele care așteaptă decizia ta, cu verdictele validatorilor.",
    )


@router.get("/productie")
def productie(request: Request, u: Agentie) -> Response:
    return pagina(
        request,
        u,
        "panou/gol.html",
        tab="productie",
        titlu="Producție",
        pictograma="⚙",
        text="Aici vei vedea fiecare livrabil pe etape, cu timpi și reîncercări.",
    )


@router.get("/alerte")
def alerte(request: Request, u: Agentie) -> Response:
    return pagina(
        request,
        u,
        "panou/gol.html",
        tab="alerte",
        titlu="Alerte",
        pictograma="!",
        text="Aici vor apărea incidentele, pe severitate, cu starea lor.",
    )


@router.get("/meniu")
def meniu(request: Request, u: Agentie) -> Response:
    return pagina(request, u, "panou/meniu.html", tab="meniu")


@router.get("/meniu/notificari")
def setari_notificari(request: Request, u: Agentie, db: DbSession) -> Response:
    s = get_settings()
    return pagina(
        request,
        u,
        "panou/notificari.html",
        tab="meniu",
        push_configurat=notificari.push_disponibil(),
        vapid_public=s.vapid_public_key if notificari.push_disponibil() else "",
        abonamente=notificari.numar_abonamente(db, u.utilizator_id),
        telegram_activ=s.telegram_activ,
    )


# --- butoanele de oprire (7.8) -----------------------------------------------------------------


def _tip(tip: str, tenant_id: str) -> tuple[Oprire, uuid.UUID | None]:
    try:
        t = Oprire(tip)
    except ValueError:
        raise HTTPException(status_code=422, detail="Tip de oprire necunoscut.") from None
    if t is not Oprire.CLIENT:
        return t, None
    try:
        return t, uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Client invalid.") from None


@router.post("/opriri/opreste", dependencies=[Depends(csrf_protect)])
def opreste(
    u: PoateOpri,
    db: DbSession,
    tip: Annotated[str, Form(max_length=40)],
    tenant_id: Annotated[str, Form(max_length=64)] = "",
    motiv: Annotated[str, Form(max_length=300)] = "",
) -> Response:
    """Direcția sigură: o atingere, imediat (în urgență nu stă nimeni pe confirmări). Auditat."""
    t, tenant = _tip(tip, tenant_id)
    if tenant is not None and not cauta_clienti(db, str(tenant)):
        raise HTTPException(status_code=422, detail="Client invalid.")
    opriri.seteaza(db, t, True, canal="panou", motiv=motiv, tenant_id=tenant, utilizator_id=u.utilizator_id)
    return RedirectResponse("/?mesaj=oprit", status_code=303)


@router.get("/opriri/confirma-pornire")
def confirma_pornire(
    request: Request, u: PoateOpri, db: DbSession, tip: str, tenant_id: str = ""
) -> Response:
    t, tenant = _tip(tip, tenant_id)
    eticheta = opriri.ETICHETE[t]
    if tenant is not None:
        gasit = cauta_clienti(db, str(tenant))
        if not gasit:
            raise HTTPException(status_code=422, detail="Client invalid.")
        eticheta = f"clientul {gasit[0].nume}"
    return pagina(
        request,
        u,
        "panou/confirmare.html",
        tab="acasa",
        titlu="Repornire",
        intrebare=f"Repornești: {eticheta}?",
        detalii="Repornirea reia activitatea oprită (direcția periculoasă). Rămâne în jurnalul de audit.",
        actiune="/opriri/porneste",
        ascunse={"tip": t.value, "tenant_id": str(tenant or "")},
        buton="Da, repornește",
        periculos=True,
        anulare="/",
    )


@router.post("/opriri/porneste", dependencies=[Depends(csrf_protect)])
def porneste(
    u: PoateOpri,
    db: DbSession,
    tip: Annotated[str, Form(max_length=40)],
    confirmare: Annotated[Literal["da"], Form()],
    tenant_id: Annotated[str, Form(max_length=64)] = "",
    motiv: Annotated[str, Form(max_length=300)] = "",
) -> Response:
    t, tenant = _tip(tip, tenant_id)
    opriri.seteaza(db, t, False, canal="panou", motiv=motiv, tenant_id=tenant, utilizator_id=u.utilizator_id)
    return RedirectResponse("/?mesaj=repornit", status_code=303)


# --- notificări push ---------------------------------------------------------------------------------------


class Chei(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=10, max_length=100)


class Abonare(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000, pattern=r"^https://")
    keys: Chei


class Dezabonare(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)


def _cere_push() -> None:
    if not notificari.push_disponibil():
        raise HTTPException(status_code=503, detail="Notificările push nu sunt configurate pe server.")


@router.post("/notificari/aboneaza", dependencies=[Depends(csrf_protect)])
def aboneaza(request: Request, u: Agentie, db: DbSession, corp: Abonare) -> dict[str, bool]:
    _cere_push()
    try:
        notificari.aboneaza(
            db,
            u.utilizator_id,
            endpoint=corp.endpoint,
            p256dh=corp.keys.p256dh,
            auth=corp.keys.auth,
            user_agent=request.headers.get("user-agent"),
        )
    except notificari.ConflictAbonament:
        raise HTTPException(
            status_code=409, detail="Dispozitivul este deja asociat altui cont; dezabonează-l mai întâi."
        ) from None
    audit.record(db, "notificari.abonare", obiect_tip="abonament_push")
    return {"ok": True}


@router.post("/notificari/dezaboneaza", dependencies=[Depends(csrf_protect)])
def dezaboneaza(u: Agentie, db: DbSession, corp: Dezabonare) -> dict[str, bool]:
    sters = notificari.dezaboneaza(db, u.utilizator_id, corp.endpoint)
    if sters:
        audit.record(db, "notificari.dezabonare", obiect_tip="abonament_push")
    return {"ok": True}


@router.post("/notificari/test", dependencies=[Depends(csrf_protect)])
def test(u: Agentie, db: DbSession) -> Response:
    _cere_push()
    if notificari.numar_abonamente(db, u.utilizator_id) == 0:
        raise HTTPException(
            status_code=409, detail="Niciun dispozitiv abonat. Pornește mai întâi notificările."
        )
    rez = notificari.trimite_utilizatorului(
        db,
        u.utilizator_id,
        notificari.Notificare(
            nivel=notificari.Nivel.INFORMATIV,
            titlu="Notificare de test",
            text="Dacă vezi acest mesaj, notificările funcționează.",
            url="/meniu/notificari",
        ),
    )
    audit.record(db, "notificari.test", obiect_tip="abonament_push", detalii={"trimise": rez.trimise})
    return JSONResponse({"trimise": rez.trimise, "sterse": rez.sterse, "esuate": rez.esuate})
