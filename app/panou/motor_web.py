"""Operare, partea de motor (18.2, ecranul 18): starea workerului și a cozilor, joburile programate, efectele
externe în așteptare sau oprite, întrerupătorul și opririle.

Citirea: orice rol de agenție; sesiunea de bază este a utilizatorului, deci efectele și pauzele se văd doar
pentru clienții la care are acces (RLS). Workerii, cozile și programările sunt ale întregului sistem (doar
numere, fără identificatori de client). Acțiunile asupra sistemului (pauză / reluare / „rulează acum” pe o
programare, reluarea unui conector) sunt ale proprietarului, cu CSRF și audit. Butoanele de oprire nu se
dublează: stau pe Acasă.
"""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.config import get_settings
from app.conturi import DbSession, SesiuneCurenta, csrf_protect, lista_clienti, require_role
from app.conturi.roluri import ROLURI_AGENTIE, Rol
from app.logging import get_logger
from app.operare import audit, efecte, motor, opriri, semnale
from app.operare.efecte import Stare as StareEfect
from app.operare.opriri import Oprire
from app.panou.sabloane import pagina

log = get_logger("app.operare_motor")
router = APIRouter(prefix="/operare/motor", tags=["operare"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
Proprietar = Annotated[SesiuneCurenta, Depends(require_role(Rol.PROPRIETAR))]

MESAJE = {
    "pauza": "Programarea a fost pusă pe pauză.",
    "reia": "Programarea a fost reluată.",
    "ruleaza": "Programarea rulează acum o dată; rezultatul apare în Alerte dacă eșuează.",
    "conector": "Pauza canalului a fost ridicată; efectele ținute pe loc pleacă în cel mult un minut.",
}
STARI_DESCHISE = (
    StareEfect.IN_ASTEPTARE,
    StareEfect.IN_TRIMITERE,
    StareEfect.ESUAT_TEMPORAR,
    StareEfect.ESUAT_DEFINITIV,
)


def _limita(d: motor.DefinitieCoada) -> str:
    parti = []
    if d.paralel_global:
        parti.append(f"{d.paralel_global} în paralel")
    if d.cereri:
        parti.append(f"{d.cereri} pe {d.perioada_sec:g} s")
    return ", ".join(parti) or "fără limită"


def _cozi() -> tuple[list[dict[str, Any]], bool]:
    try:
        adancimi = {a.nume: a for a in motor.adancime_cozi()}
        ok = True
    except Exception as exc:
        log.warning("motorul nu a răspuns", extra={"tip_eroare": type(exc).__name__})
        adancimi, ok = {}, False
    definitii = {d.nume: d for d in motor.definitii_cozi()}
    randuri = []
    for nume in [*definitii, *(n for n in adancimi if n not in definitii)]:
        a = adancimi.get(nume)
        d = definitii.get(nume)
        randuri.append(
            {
                "nume": nume,
                "in_coada": a.in_coada if a else 0,
                "in_lucru": a.in_lucru if a else 0,
                "limita": _limita(d) if d else "–",
            }
        )
    return randuri, ok


def _programari() -> tuple[list[motor.InfoProgramare], bool]:
    try:
        return motor.lista_programari(), True
    except Exception as exc:
        log.warning("programările nu s-au putut citi", extra={"tip_eroare": type(exc).__name__})
        return [], False


def _date_stare(db: DbSession) -> dict[str, Any]:
    cozi, motor_ok = _cozi()
    return {
        "workeri": semnale.stare_workeri(db, get_settings().worker_timeout_sec),
        "cozi": cozi,
        "motor_ok": motor_ok,
    }


@router.get("/fragment")
def fragment(request: Request, u: Agentie, db: DbSession) -> Response:
    return pagina(request, u, "panou/_motor_stare.html", tab="meniu", **_date_stare(db))


@router.get("")
def operare_motor(request: Request, u: Agentie, db: DbSession, mesaj: str = "") -> Response:
    programari, programari_ok = _programari()
    nume_client = {c.id: c.nume for c in lista_clienti(db)}
    deschise = efecte.listeaza(db, stari=STARI_DESCHISE, limita=50)
    active = opriri.active(db)
    productie_oprita = opriri.citeste(db, Oprire.PRODUCTIE)
    return pagina(
        request,
        u,
        "panou/operare_motor.html",
        tab="meniu",
        mesaj=MESAJE.get(mesaj, ""),
        programari=programari,
        programari_ok=programari_ok,
        poate_actiona=u.rol is Rol.PROPRIETAR,
        efecte_pe_stare=[(efecte.ETICHETE[s], n) for s, n in _numara(db)],
        efecte_deschise=[
            {
                "e": e,
                "client": nume_client.get(e.tenant_id, "–"),
                "eticheta": efecte.ETICHETE[StareEfect(e.stare)],
            }
            for e in deschise
        ],
        pauze=[{"p": p, "client": nume_client.get(p.tenant_id, "–")} for p in efecte.pauze(db)],
        opriri_active=[
            {
                "tip": o.tip,
                "eticheta": opriri.ETICHETE[Oprire(o.tip)],
                "client": nume_client.get(o.tenant_id, "–") if o.tenant_id else "–",
            }
            for o in active
        ],
        intrerupator_oprit=bool(productie_oprita and productie_oprita.activ),
        intrerupator_motiv=productie_oprita.motiv if productie_oprita and productie_oprita.activ else "",
        **_date_stare(db),
    )


def _numara(db: DbSession) -> list[tuple[StareEfect, int]]:
    contoare = efecte.numara_pe_stare(db)
    return [(s, contoare[s.value]) for s in StareEfect if contoare.get(s.value)]


# --- acțiuni (proprietar)
# -----------------------------------------------------------------------------------------


@router.post("/programari/{nume}/{actiune}", dependencies=[Depends(csrf_protect)])
def actiune_programare(
    u: Proprietar, db: DbSession, nume: str, actiune: Literal["pauza", "reia", "ruleaza"]
) -> Response:
    if nume not in {p.nume for p in motor.lista_programari()}:
        raise HTTPException(status_code=404, detail="Programarea nu există.")
    detalii: dict[str, Any] = {"programare": nume}
    if actiune == "pauza":
        motor.pune_pe_pauza(nume)
    elif actiune == "reia":
        motor.reia_programarea(nume)
    else:
        detalii["job"] = motor.declanseaza_acum(nume)
    audit.record(
        db, f"programare.{actiune}", obiect_tip="programare", obiect_id=nume, utilizator_id=u.utilizator_id,
        tenant_id=None, detalii=detalii,
    )  # fmt: skip
    return RedirectResponse(f"/operare/motor?mesaj={actiune}", status_code=303)


@router.post("/conectori/reia", dependencies=[Depends(csrf_protect)])
def reia_conectorul(
    u: Proprietar,
    db: DbSession,
    tenant_id: Annotated[str, Form(max_length=64)],
    canal: Annotated[str, Form(max_length=41, pattern=r"^[a-z][a-z0-9_]{1,40}$")],
) -> Response:
    try:
        tenant = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Client invalid.") from None
    if not efecte.reia_conectorul(db, tenant, canal, utilizator_id=u.utilizator_id):
        raise HTTPException(status_code=404, detail="Canalul nu este pe pauză.")
    return RedirectResponse("/operare/motor?mesaj=conector", status_code=303)
