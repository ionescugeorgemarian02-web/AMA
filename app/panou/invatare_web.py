"""Ecranul „Învățare” (docs/18, ecranul 12; docs/11 §11.7), F11.6.

- `/invatare`: starea înghețării și lecțiile propuse care așteaptă curatoriere, cu dovezile fiecăreia.
- `/invatare?client=<id>`: lecțiile active ale clientului, istoricul promovărilor și al revenirilor,
  registrul de experimente și starea alegerii adaptive (tipar de hook, slot).
- `POST /invatare/lectie/<id>/aproba | respinge | retrage`, `POST /invatare/ingheata`,
  `POST /invatare/experiment/<client>` (declară) și `POST /invatare/experiment/<id>/opreste`.

Citirea cere `invatare.citeste`. Deciziile le ia doar proprietarul (CSRF). Regulile (o promovare pe
săptămână pe domeniu, înghețarea, plafonul de lecții) sunt în `app.invatare`, nu aici: ecranul doar arată
refuzul. Rulările optimizatorului și scorurile pe seturile de aur (11.7) țin de treptele următoare de
învățare și nu există încă.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.conturi import (
    DbSession,
    Permisiune,
    Rol,
    SesiuneCurenta,
    csrf_protect,
    lista_clienti,
    require_permission,
    require_role,
)
from app.invatare import alegere, constitutie, curator, experimente, reflector
from app.invatare.constitutie import ConstitutieIncalcata
from app.invatare.curator import CuratorRefuzat
from app.invatare.experimente import ExperimentRefuzat
from app.panou.sabloane import pagina

router = APIRouter(prefix="/invatare", tags=["invatare"])
PoateCiti = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.INVATARE_CITESTE))]
Proprietar = Annotated[SesiuneCurenta, Depends(require_role(Rol.PROPRIETAR))]
MESAJE = {
    "aprobata": "Lecția a fost aprobată și intră în contextul autorului.",
    "respinsa": "Lecția a fost respinsă.",
    "retrasa": "Promovarea a fost anulată: lecția nu mai intră în context.",
    "inghetat": "Învățarea este înghețată: nicio promovare până la dezghețare.",
    "dezghetat": "Învățarea a fost dezghețată.",
    "experiment": "Experimentul a fost declarat.",
    "oprit": "Experimentul a fost oprit.",
}
ETICHETE_STARE_LECTIE = {"activa": "activă", "retrasa": "retrasă", "respinsa": "respinsă"}
ETICHETE_SURSA = {
    "rezultate": "din rezultatele postărilor",
    "verdicte": "din verdictele validatorilor",
    "decizii": "din deciziile oamenilor",
}
ETICHETE_DIMENSIUNE = {
    "tipar_hook": "Tiparul de hook",
    "slot": "Slotul",
    "format": "Formatul",
    "canal": "Canalul",
}
ETICHETE_STARE_EXPERIMENT = {"in_curs": "în curs", "incheiat": "încheiat", "oprit": "oprit"}


def _id(text: str, ce: str = "Lecție inexistentă.") -> uuid.UUID:
    try:
        return uuid.UUID(text)
    except ValueError:
        raise HTTPException(status_code=404, detail=ce) from None


def _inapoi(tenant_id: uuid.UUID | None, mesaj: str) -> RedirectResponse:
    client = f"client={tenant_id}&" if tenant_id else ""
    return RedirectResponse(f"/invatare?{client}mesaj={mesaj}", status_code=303)


def _ecran(
    request: Request,
    u: SesiuneCurenta,
    db: Any,
    client: uuid.UUID | None,
    *,
    status: int = 200,
    eroare: str = "",
) -> Response:
    clienti = {c.id: c.nume for c in lista_clienti(db)}
    if client is not None and client not in clienti:
        raise HTTPException(status_code=404, detail="Client necunoscut.")
    context: dict[str, Any] = {}
    if client is not None:
        context = {
            "active": curator.active(db, client),
            "istoric": curator.istoric(db, client),
            "experimente": experimente.ale_clientului(db, client),
            "variante": {d: alegere.variante_client(db, client, d) for d in alegere.DIMENSIUNI},
        }
    return pagina(
        request,
        u,
        "panou/invatare.html",
        tab="meniu",
        status=status,
        clienti=clienti,
        client=client,
        propuneri=reflector.propuneri(db, client),
        inghetat=constitutie.inghetat(db),
        mesaj=MESAJE.get(request.query_params.get("mesaj", ""), ""),
        eroare=eroare,
        etichete_stare_lectie=ETICHETE_STARE_LECTIE,
        etichete_sursa=ETICHETE_SURSA,
        etichete_dimensiune=ETICHETE_DIMENSIUNE,
        etichete_stare_experiment=ETICHETE_STARE_EXPERIMENT,
        etichete_concluzie=experimente.ETICHETE_CONCLUZIE,
        dimensiuni_experiment=experimente.DIMENSIUNI,
        explorare=alegere.EXPLORARE,
        publicari_minime=alegere.PUBLICARI_MINIME,
        **context,
    )


@router.get("")
def ecran(request: Request, u: PoateCiti, db: DbSession, client: str = "") -> Response:
    return _ecran(request, u, db, _id(client, "Client necunoscut.") if client else None)


@router.post("/lectie/{lectie_id}/{actiune}", dependencies=[Depends(csrf_protect)])
async def decide(request: Request, lectie_id: str, actiune: str, u: Proprietar, db: DbSession) -> Response:
    lid = _id(lectie_id)
    motiv = str((await request.form()).get("motiv") or "")
    client: uuid.UUID | None = None
    try:
        if actiune == "aproba":
            r = curator.aproba(db, lid, utilizator_id=u.utilizator_id, rol=u.rol)
            mesaj = "aprobata"
        elif actiune == "respinge":
            r = curator.respinge(db, lid, utilizator_id=u.utilizator_id, motiv=motiv)
            mesaj = "respinsa"
        elif actiune == "retrage":
            r = curator.retrage(db, lid, utilizator_id=u.utilizator_id, motiv=motiv)
            mesaj = "retrasa"
        else:
            raise HTTPException(status_code=404, detail="Acțiune necunoscută.")
        client = r.tenant_id
    except (CuratorRefuzat, ConstitutieIncalcata) as exc:
        return _ecran(request, u, db, None, status=422, eroare=str(exc).capitalize() + ".")
    return _inapoi(client, mesaj)


@router.post("/ingheata", dependencies=[Depends(csrf_protect)])
async def ingheata(request: Request, u: Proprietar, db: DbSession) -> Response:
    f = await request.form()
    activ = str(f.get("activ") or "") == "1"
    try:
        constitutie.ingheata(db, activ=activ, utilizator_id=u.utilizator_id, motiv=str(f.get("motiv") or ""))
    except ConstitutieIncalcata as exc:
        return _ecran(request, u, db, None, status=422, eroare=str(exc).capitalize() + ".")
    return _inapoi(None, "inghetat" if activ else "dezghetat")


@router.post("/experiment/{client}", dependencies=[Depends(csrf_protect)])
async def declara_experiment(request: Request, client: str, u: Proprietar, db: DbSession) -> Response:
    tid = _id(client, "Client necunoscut.")
    f = await request.form()
    try:
        minim = int(str(f.get("minim_pe_varianta") or "10"))
        durata = int(str(f.get("durata_maxima_zile") or "60"))
        experimente.declara(
            db,
            tid,
            ipoteza=str(f.get("ipoteza") or ""),
            dimensiune=str(f.get("dimensiune") or ""),
            varianta_a=str(f.get("varianta_a") or ""),
            varianta_b=str(f.get("varianta_b") or ""),
            minim_pe_varianta=minim,
            durata_maxima_zile=durata,
            utilizator_id=u.utilizator_id,
        )
    except ValueError as exc:  # și `ExperimentRefuzat`, și un număr scris greșit
        text = str(exc) if isinstance(exc, ExperimentRefuzat) else "regula de oprire cere numere întregi"
        return _ecran(request, u, db, tid, status=422, eroare=text.capitalize() + ".")
    return _inapoi(tid, "experiment")


@router.post("/experiment/{experiment_id}/opreste", dependencies=[Depends(csrf_protect)])
async def opreste_experiment(request: Request, experiment_id: str, u: Proprietar, db: DbSession) -> Response:
    eid = _id(experiment_id, "Experiment inexistent.")
    try:
        e = experimente.opreste(
            db, eid, utilizator_id=u.utilizator_id, motiv=str((await request.form()).get("motiv") or "")
        )
    except ExperimentRefuzat as exc:
        return _ecran(request, u, db, None, status=422, eroare=str(exc).capitalize() + ".")
    return _inapoi(e.tenant_id, "oprit")
