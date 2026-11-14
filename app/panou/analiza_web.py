"""Ecranul „Rapoarte și analiză” (docs/18, ecranul 17), prima parte (F10.1, F10.2): postările măsurate, cu
cifrele pe intervale ale fiecăreia și curba de retenție a clipurilor (unde platforma o dă).

- `/analiza`: postările cu cifre, cele mai recente primele.
- `/analiza/livrabil/<id>`: cifrele pe intervale (1 oră … 28 de zile), cu starea fiecărui interval (citit,
  ratat, indisponibil) și sursa (platformă sau om), curba de retenție desenată pe server și rezumatul ei.
- `/analiza/etichete?dupa=tipar_hook`: postările sortate și grupate după tiparul de hook, format, slot,
  pilon, unghi sau canal, cu recompensa fiecăreia și media pe grup (F10.3); opțional pe un singur client.
- `/analiza/clienti`: tabloul de bord (F10.4): indicatorii de business din 4.13 pe fiecare client și scorul
  de sănătate cu semnalele de risc din 4.10; clienții cu probleme apar primii.
- `POST /analiza/livrabil/<id>/metrici`: cifre introduse de om din exportul platformei, pentru canalele
  fără citire prin API (CSRF; permisiunea `livrabil.editeaza`).
Citirea cere `rapoarte.citeste`.
"""

import datetime as dt
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import productie
from app.analiza import colector, etichete, retentie, sanatate, trafic
from app.cercetare import tendinte
from app.connectors.contract import CHEI_METRICI, ETICHETE_METRICI
from app.conturi import (
    DbSession,
    Permisiune,
    SesiuneCurenta,
    csrf_protect,
    lista_clienti,
    require_permission,
    require_role,
)
from app.conturi.roluri import ROLURI_AGENTIE, poate
from app.panou.sabloane import pagina

router = APIRouter(prefix="/analiza", tags=["analiza"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
PoateCiti = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.RAPOARTE_CITESTE))]
PoateEdita = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.LIVRABIL_EDITEAZA))]
MESAJE = {
    "salvat": "Cifrele au fost salvate.",
    "profil": "Profilul de nișă a fost salvat.",
    "inbox": "Am primit. Devine fișă la următoarea rulare (dimineața).",
}


def _id(text: str) -> uuid.UUID:
    try:
        return uuid.UUID(text)
    except ValueError:
        raise HTTPException(status_code=404, detail="Livrabil inexistent.") from None


def _procent(valoare: float) -> str:
    return f"{valoare * 100:.0f}%"


@router.get("")
def lista(request: Request, u: Agentie, _p: PoateCiti, db: DbSession) -> Response:
    clienti = {c.id: c.nume for c in lista_clienti(db)}
    return pagina(
        request,
        u,
        "panou/analiza.html",
        tab="meniu",
        randuri=colector.recente(db, limita=50),
        clienti=clienti,
        etichete_metrici=ETICHETE_METRICI,
        etichete_interval=colector.ETICHETE_INTERVAL,
    )


@router.get("/clienti")
def tablou_clienti(request: Request, u: Agentie, _p: PoateCiti, db: DbSession) -> Response:
    return pagina(
        request,
        u,
        "panou/analiza_clienti.html",
        tab="meniu",
        agentie=sanatate.situatie(db),
        niveluri=sanatate.NIVELURI,
        tinte=sanatate.TINTE,
    )


@router.get("/trafic")
def trafic_propriu(request: Request, u: Agentie, _p: PoateCiti, db: DbSession, zile: int = 30) -> Response:
    """Pâlnia site-ului (F10.6): vizite cu acord → cereri de audit → confirmate → audituri → clienți."""
    zile = max(1, min(zile, 365))
    azi = dt.datetime.now(dt.UTC).date()
    return pagina(
        request,
        u,
        "panou/analiza_trafic.html",
        tab="meniu",
        p=trafic.palnie(db, azi - dt.timedelta(days=zile - 1), azi),
        zile=zile,
    )


@router.get("/etichete")
def pe_etichete(
    request: Request, u: Agentie, _p: PoateCiti, db: DbSession, dupa: str = "tipar_hook", client: str = ""
) -> Response:
    if dupa not in etichete.GRUPARI:
        raise HTTPException(status_code=422, detail="Grupare necunoscută.")
    clienti = {c.id: c.nume for c in lista_clienti(db)}
    tenant_id: uuid.UUID | None = None
    if client:
        try:
            tenant_id = uuid.UUID(client)
        except ValueError:
            raise HTTPException(status_code=422, detail="Client necunoscut.") from None
    grupuri = etichete.grupeaza(db, dupa, tenant_id=tenant_id)
    return pagina(
        request,
        u,
        "panou/analiza_etichete.html",
        tab="meniu",
        grupuri=[(g, g.medii()) for g in grupuri],
        dupa=dupa,
        grupari=etichete.GRUPARI,
        client=client,
        clienti=clienti,
        etichete_recompensa=etichete.ETICHETE_RECOMPENSA,
        valoare=etichete.valoare,
        eticheta_slot=etichete.eticheta_slot,
        etichete_hook=etichete.ETICHETE_HOOK,
    )


def _detaliu(
    request: Request,
    u: SesiuneCurenta,
    db: DbSession,
    livrabil_id: uuid.UUID,
    *,
    status: int = 200,
    **extra: Any,
) -> Response:
    lv = productie.citeste(db, livrabil_id)
    if lv is None:
        raise HTTPException(status_code=404, detail="Livrabil inexistent.")
    citiri = {r.interval: r for r in colector.ale_livrabilului(db, livrabil_id) if r.canal == lv.canal}
    chei = [k for k in CHEI_METRICI if any(k in r.valori for r in citiri.values())]
    curba = retentie.a_livrabilului(db, livrabil_id, lv.canal)
    grafic: dict[str, Any] | None = None
    if curba is not None:
        p = retentie.puncte(curba)
        linie, varf = retentie.linie_svg(p)
        r = retentie.rezumat(p)
        grafic = {
            "linie": linie,
            "varf": _procent(varf),
            "latime": retentie.LATIME,
            "inaltime": retentie.INALTIME,
            "medie": _procent(r.medie),
            "dupa_hook": _procent(r.dupa_hook),
            "la_final": _procent(r.la_final),
            "cadere_pozitie": _procent(r.cadere_pozitie),
            "cadere_marime": _procent(r.cadere_marime),
            "are_cadere": r.cadere_marime > 0,
            "citit_la": curba.citit_la,
            "puncte": len(p),
        }
    return pagina(
        request,
        u,
        "panou/analiza_livrabil.html",
        tab="meniu",
        status=status,
        livrabil=lv,
        eticheta_stare=productie.stari.ETICHETE.get(productie.Stare(lv.stare), lv.stare),
        intervale=[cod for cod, _ in colector.INTERVALE],
        etichete_interval=colector.ETICHETE_INTERVAL,
        etichete_metrici=ETICHETE_METRICI,
        toate_cheile=CHEI_METRICI,
        citiri=citiri,
        chei=chei,
        grafic=grafic,
        poate_edita=poate(u.rol, Permisiune.LIVRABIL_EDITEAZA),
        **extra,
    )


@router.get("/livrabil/{livrabil_id}")
def detaliu(
    request: Request, livrabil_id: str, u: Agentie, _p: PoateCiti, db: DbSession, mesaj: str = ""
) -> Response:
    return _detaliu(request, u, db, _id(livrabil_id), mesaj=MESAJE.get(mesaj, ""))


@router.post("/livrabil/{livrabil_id}/metrici", dependencies=[Depends(csrf_protect)])
async def introduce(
    request: Request, livrabil_id: str, u: Agentie, _p: PoateEdita, db: DbSession
) -> Response:
    lid = _id(livrabil_id)
    lv = productie.citeste(db, lid)
    if lv is None:
        raise HTTPException(status_code=404, detail="Livrabil inexistent.")
    formular = await request.form()
    valori: dict[str, Any] = {}
    try:
        for cheie in CHEI_METRICI:
            brut = str(formular.get(cheie) or "").strip().replace(".", "").replace(" ", "")
            if brut:
                if not brut.isdecimal():
                    raise colector.MetriciRefuzate(
                        f"„{ETICHETE_METRICI[cheie]}” trebuie să fie un număr întreg, fără semn."
                    )
                valori[cheie] = int(brut)
        colector.inregistreaza_manual(
            db, lid, lv.canal, str(formular.get("interval") or ""), valori, utilizator_id=u.utilizator_id
        )
    except colector.MetriciRefuzate as exc:
        return _detaliu(request, u, db, lid, status=422, eroare=str(exc))
    return RedirectResponse(f"/analiza/livrabil/{lid}?mesaj=salvat", status_code=303)


# --- tendințe (F10.7) -----------------------------------------------------------------------------------
def _client(text: str) -> uuid.UUID:
    try:
        return uuid.UUID(text)
    except ValueError:
        raise HTTPException(status_code=404, detail="Client necunoscut.") from None


def _tendinte(
    request: Request,
    u: SesiuneCurenta,
    db: DbSession,
    tenant_id: uuid.UUID | None,
    *,
    status: int = 200,
    **extra: Any,
) -> Response:
    clienti = {c.id: c.nume for c in lista_clienti(db)}
    if tenant_id is not None and tenant_id not in clienti:
        raise HTTPException(status_code=404, detail="Client necunoscut.")
    return pagina(
        request,
        u,
        "panou/analiza_tendinte.html",
        tab="meniu",
        status=status,
        clienti=clienti,
        client=tenant_id,
        profil=tendinte.profil(db, tenant_id) if tenant_id else None,
        fise=tendinte.ale_clientului(db, tenant_id) if tenant_id else [],
        poate_edita=poate(u.rol, Permisiune.LIVRABIL_EDITEAZA),
        **extra,
    )


@router.get("/tendinte")
def ecran_tendinte(
    request: Request, u: Agentie, _p: PoateCiti, db: DbSession, client: str = "", mesaj: str = ""
) -> Response:
    return _tendinte(request, u, db, _client(client) if client else None, mesaj=MESAJE.get(mesaj, ""))


@router.post("/tendinte/{client}/profil", dependencies=[Depends(csrf_protect)])
async def salveaza_profil(
    request: Request, client: str, u: Agentie, _p: PoateEdita, db: DbSession
) -> Response:
    tid = _client(client)
    f = await request.form()
    try:
        tendinte.seteaza_profil(
            db,
            tid,
            termeni=str(f.get("termeni") or "").replace("\n", ",").split(","),
            fluxuri=str(f.get("fluxuri") or "").split(),
            utilizator_id=u.utilizator_id,
        )
    except tendinte.ProfilInvalid as exc:
        return _tendinte(request, u, db, tid, status=422, eroare=str(exc))
    return RedirectResponse(f"/analiza/tendinte?client={tid}&mesaj=profil", status_code=303)


@router.post("/tendinte/{client}/inbox", dependencies=[Depends(csrf_protect)])
async def adauga_in_inbox(
    request: Request, client: str, u: Agentie, _p: PoateEdita, db: DbSession
) -> Response:
    from app.media import tendinte as inbox

    tid = _client(client)
    f = await request.form()
    try:
        inbox.adauga(db, tid, str(f.get("text") or ""), utilizator_id=u.utilizator_id)
    except inbox.TendintaInvalida as exc:
        return _tendinte(request, u, db, tid, status=422, eroare=str(exc))
    return RedirectResponse(f"/analiza/tendinte?client={tid}&mesaj=inbox", status_code=303)
