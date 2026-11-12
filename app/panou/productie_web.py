"""Ecranul Producție (18.2, 18.4): lista livrabilelor și „urma” fiecăruia, cu „reia” și „anulează”.

Lista: filtre pe client, stare și excepții, cu paginare. Detaliul („urma”): istoricul tranzițiilor, inclusiv
refuzurile, pașii fluxului durabil (stare, durată, eroare), cererile de aprobare, efectele externe și starea
lor și contoarele limitelor anti-buclă. Sesiunea de bază este a utilizatorului: izolarea pe client (RLS) se
aplică, deci un operator vede doar clientul la care are acces. Acțiunile cer permisiunea `livrabil.editeaza`,
CSRF, un motiv și lasă urmă în audit.
"""

import datetime as dt
import uuid
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select

from app import productie
from app.config import get_settings
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
from app.logging import get_logger
from app.operare import audit, coada_erori, efecte, motor
from app.operare.efecte import ETICHETE as ETICHETE_EFECT
from app.operare.efecte import Stare as StareEfect
from app.panou.sabloane import pagina as randeaza
from app.productie import Stare, aprobari, limite
from app.productie.reguli_aprobare import ETICHETE_DECIDENT, ETICHETE_STARE

log = get_logger("app.productie_web")
router = APIRouter(prefix="/productie", tags=["productie"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
PoateEdita = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.LIVRABIL_EDITEAZA))]

PE_PAGINA = 20
MOTIV_MAXIM = 300
MAXIM_JOBURI_AFISATE = 6
MESAJE = {
    "reluat": "Reluarea a fost înregistrată.",
    "pas_reluat": "Pasul eșuat a fost reluat. Jobul continuă de la acel pas; pașii încheiați nu se repetă.",
    "anulat": "Livrabilul a fost anulat.",
}
CLASA_STARE = {
    "inchis": "ok",
    "publicat": "ok",
    "in_masurare": "ok",
    "respins": "pericol",
    "carantina": "pericol",
    "coada_de_erori": "pericol",
    "esec_temporar": "atentie",
    "expirat": "atentie",
    "anulat": "",
}
CLASA_EFECT = {"trimis": "ok", "esuat_definitiv": "pericol", "esuat_temporar": "atentie", "anulat": ""}
ETICHETE_JOB = {
    "amanat": "amânat",
    "in_coada": "în coadă",
    "in_lucru": "în lucru",
    "terminat": "terminat",
    "esuat": "eșuat",
    "anulat": "anulat",
    "epuizat": "epuizat (căderi repetate)",
    "suspendat": "suspendat",
}
CLASA_JOB = {"terminat": "ok", "esuat": "pericol", "epuizat": "pericol", "in_lucru": "atentie"}


def _uuid(valoare: str) -> uuid.UUID:
    try:
        return uuid.UUID(valoare)
    except ValueError:
        raise HTTPException(status_code=404, detail="Livrabilul nu există.") from None


def _durata(inceput: dt.datetime | None, sfarsit: dt.datetime | None) -> str:
    if inceput is None or sfarsit is None:
        return "–"
    sec = (sfarsit - inceput).total_seconds()
    return f"{sec * 1000:.0f} ms" if sec < 1 else f"{sec:.1f} s"


# --- lista
# ---------------------------------------------------------------------------------------------------------


@router.get("")
def lista(
    request: Request,
    u: Agentie,
    db: DbSession,
    client: str = "",
    stare: str = "",
    exceptii: str = "",
    pagina: Annotated[int, Query(ge=1, le=10_000)] = 1,
    mesaj: str = "",
) -> Response:
    q = select(productie.Livrabil)
    if client:
        try:
            q = q.where(productie.Livrabil.tenant_id == uuid.UUID(client))
        except ValueError:
            raise HTTPException(status_code=422, detail="Client invalid.") from None
    if stare:
        try:
            q = q.where(productie.Livrabil.stare == Stare(stare).value)
        except ValueError:
            raise HTTPException(status_code=422, detail="Stare necunoscută.") from None
    solo_exceptii = exceptii == "1"
    if solo_exceptii:
        q = q.where(productie.Livrabil.stare.in_([s.value for s in productie.EXCEPTII]))
    q = (
        q.order_by(productie.Livrabil.actualizat_la.desc(), productie.Livrabil.id.desc())
        .offset((pagina - 1) * PE_PAGINA)
        .limit(PE_PAGINA + 1)
    )
    randuri = list(db.execute(q).scalars())
    urmeaza = len(randuri) > PE_PAGINA
    clienti = lista_clienti(db)
    nume_client = {c.id: c.nume for c in clienti}
    filtre = {
        k: v
        for k, v in (("client", client), ("stare", stare), ("exceptii", "1" if solo_exceptii else ""))
        if v
    }

    def legatura(p: int) -> str:
        return "/productie?" + urlencode({**filtre, "pagina": p})

    return randeaza(
        request,
        u,
        "panou/productie.html",
        tab="productie",
        livrabile=[
            {
                "l": liv,
                "client": nume_client.get(liv.tenant_id, "–"),
                "eticheta": productie.ETICHETE[Stare(liv.stare)],
                "clasa": CLASA_STARE.get(liv.stare, ""),
            }
            for liv in randuri[:PE_PAGINA]
        ],
        clienti=clienti,
        stari=[(s.value, productie.ETICHETE[s]) for s in (*productie.NORMALE, *productie.EXCEPTII)],
        client_ales=client,
        stare_aleasa=stare,
        exceptii=solo_exceptii,
        pagina=pagina,
        anterioara=legatura(pagina - 1) if pagina > 1 else None,
        urmatoarea=legatura(pagina + 1) if urmeaza else None,
        mesaj=MESAJE.get(mesaj, ""),
    )


# --- urma unui livrabil
# ----------------------------------------------------------------------------------------------


def _livrabil(db: DbSession, lid: str) -> productie.Livrabil:
    livrabil = productie.citeste(db, _uuid(lid))
    if livrabil is None:  # inexistent sau al altui client (RLS)
        raise HTTPException(status_code=404, detail="Livrabilul nu există.")
    return livrabil


def _joburi(
    livrabil: productie.Livrabil, efecte_liv: list[efecte.Efect]
) -> tuple[list[motor.DetaliiJob], bool]:
    """Joburile durabile ale livrabilului și ale efectelor lui (după identificatori). `False` dacă
    motorul nu răspunde."""
    try:
        gasite = motor.joburi_pentru([str(livrabil.id), *(str(e.id) for e in efecte_liv)])
    except Exception as exc:
        log.warning("motorul nu a răspuns", extra={"tip_eroare": type(exc).__name__})
        return [], False
    return gasite, True


def _pasi(joburi: list[motor.DetaliiJob]) -> dict[str, list[dict[str, object]]]:
    iesire: dict[str, list[dict[str, object]]] = {}
    for j in joburi[:MAXIM_JOBURI_AFISATE]:
        try:
            pasi = motor.pasi_job(j.id)
        except Exception as exc:
            log.warning("pașii jobului nu s-au putut citi", extra={"tip_eroare": type(exc).__name__})
            pasi = []
        iesire[j.id] = [
            {
                "nr": p.nr,
                "nume": p.nume,
                "stare": "eroare" if p.esuat else "ok",
                "durata": _durata(p.inceput, p.sfarsit),
                "eroare": f"{p.eroare_tip}: {p.eroare_mesaj}" if p.esuat else "",
                "esuat": p.esuat,
            }
            for p in pasi
        ]
    return iesire


def _de_reluat(db: DbSession, joburi: list[motor.DetaliiJob]) -> list[motor.DetaliiJob]:
    """Joburile eșuate sau epuizate care nu au fost deja reluate (reluarea unui job eșuat face o bifurcare:
    originalul rămâne `eșuat`, dar are un urmaș) și a căror intrare din coada de erori nu e marcată
    reluată / închisă."""
    bifurcate = {j.bifurcat_din for j in joburi if j.bifurcat_din}
    rezultat = []
    for j in joburi:
        if j.stare not in (motor.StareJob.ESUAT, motor.StareJob.EPUIZAT) or j.id in bifurcate:
            continue
        intrare = coada_erori.dupa_cheie(db, j.id)
        if intrare is not None and intrare.stare != coada_erori.Stare.NOUA.value:
            continue
        rezultat.append(j)
    return rezultat


def _detaliu(
    request: Request,
    u: SesiuneCurenta,
    db: DbSession,
    livrabil: productie.Livrabil,
    *,
    status: int = 200,
    **extra: object,
) -> Response:
    stare_l = Stare(livrabil.stare)
    efecte_liv = efecte.ale_livrabilului(db, livrabil.id)
    joburi, motor_ok = _joburi(livrabil, efecte_liv)
    de_reluat = _de_reluat(db, joburi) if motor_ok else []
    cfg = get_settings()
    contoare = limite.Limite(runde_reparatie=cfg.productie_runde_reparatie, predari=cfg.productie_predari_max)
    clienti = {c.id: c.nume for c in lista_clienti(db)}
    pauze = {(p.tenant_id, p.canal) for p in efecte.pauze(db)}
    return randeaza(
        request,
        u,
        "panou/livrabil.html",
        tab="productie",
        status=status,
        l=livrabil,
        client=clienti.get(livrabil.tenant_id, "–"),
        eticheta=productie.ETICHETE[stare_l],
        clasa_stare=CLASA_STARE.get(livrabil.stare, ""),
        etichete_stari=productie.ETICHETE,
        tranzitii=productie.istoric(db, livrabil.id),
        joburi=joburi,
        motor_ok=motor_ok,
        pasi=_pasi(joburi),
        etichete_job=ETICHETE_JOB,
        clasa_job=CLASA_JOB,
        cereri=aprobari.ale_livrabilului(db, livrabil.id),
        etichete_aprobare=ETICHETE_STARE,
        etichete_decident=ETICHETE_DECIDENT,
        efecte=efecte_liv,
        etichete_efect=ETICHETE_EFECT,
        clasa_efect=CLASA_EFECT,
        canal_pe_pauza=any((livrabil.tenant_id, e.canal) in pauze for e in efecte_liv),
        contoare=contoare,
        poate_edita=poate(u.rol, Permisiune.LIVRABIL_EDITEAZA),
        poate_reia_de_om=stare_l is Stare.COADA_DE_ERORI,
        de_reluat=de_reluat,
        poate_anula=productie.este_permisa(stare_l, Stare.ANULAT),
        **extra,
    )


@router.get("/{lid}")
def detaliu(request: Request, u: Agentie, db: DbSession, lid: str, mesaj: str = "") -> Response:
    return _detaliu(request, u, db, _livrabil(db, lid), mesaj=MESAJE.get(mesaj, ""))


# --- acțiuni
# ----------------------------------------------------------------------------------------------------------


def _motiv(valoare: str) -> str | None:
    m = valoare.strip()
    return m if len(m) >= 3 else None


@router.post("/{lid}/reia", dependencies=[Depends(csrf_protect)])
def reia(
    request: Request,
    u: PoateEdita,
    db: DbSession,
    lid: str,
    ce: Annotated[str, Form(pattern="^(livrabil|job)$")],
    motiv: Annotated[str, Form(max_length=MOTIV_MAXIM)] = "",
    job: Annotated[str, Form(max_length=200)] = "",
    de_la_pas: Annotated[str, Form(max_length=6)] = "",
) -> Response:
    """`ce=livrabil`: un om reia un livrabil din coada de erori (`productie.reia_de_om`, plus efectul
    extern eșuat).
    `ce=job`: reia un job durabil eșuat al livrabilului, de la pasul eșuat sau ales. Motiv obligatoriu;
    audit."""
    livrabil = _livrabil(db, lid)
    motiv_curat = _motiv(motiv)
    if motiv_curat is None:
        return _detaliu(
            request, u, db, livrabil, status=422, eroare="Scrie motivul reluării (cel puțin 3 caractere)."
        )
    if ce == "livrabil":
        try:
            efecte.reia_livrabilul(db, livrabil.id, utilizator_id=u.utilizator_id, motiv=motiv_curat)
        except productie.TranzitieRefuzata as exc:
            return _detaliu(request, u, db, livrabil, status=409, eroare=str(exc))
        return RedirectResponse(f"/productie/{livrabil.id}?mesaj=reluat", status_code=303)
    joburi, motor_ok = _joburi(livrabil, efecte.ale_livrabilului(db, livrabil.id))
    candidat = next((j for j in _de_reluat(db, joburi) if j.id == job), None) if motor_ok else None
    if candidat is None:  # nu e un job eșuat al ACESTUI livrabil (sau a fost deja reluat)
        return _detaliu(request, u, db, livrabil, status=409, eroare="Nu există un pas eșuat de reluat.")
    pas: int | None = None
    if de_la_pas.strip():
        if not de_la_pas.strip().isdigit():
            raise HTTPException(status_code=422, detail="Pas invalid.")
        pas = int(de_la_pas)
    try:
        continua_ca = motor.reia_job(candidat.id, pas)
    except motor.JobNereluabil as exc:
        return _detaliu(request, u, db, livrabil, status=409, eroare=str(exc))
    except Exception as exc:
        log.warning("reluare nereușită", extra={"tip_eroare": type(exc).__name__})
        return _detaliu(
            request,
            u,
            db,
            livrabil,
            status=503,
            eroare="Motorul nu a răspuns. Încearcă din nou în câteva secunde.",
        )
    intrare = coada_erori.dupa_cheie(db, candidat.id)
    if intrare is not None and intrare.stare != coada_erori.Stare.INCHISA.value:
        coada_erori.marcheaza_reluata(
            db,
            intrare,
            reluat_ca=None if continua_ca == candidat.id else continua_ca,
            utilizator_id=u.utilizator_id,
        )
    audit.record(
        db,
        "livrabil.pas_reluat",
        obiect_tip="livrabil",
        obiect_id=livrabil.id,
        utilizator_id=u.utilizator_id,
        tenant_id=livrabil.tenant_id,
        detalii={"job": candidat.id, "continua_ca": continua_ca, "de_la_pas": pas, "motiv": motiv_curat},
    )
    return RedirectResponse(f"/productie/{livrabil.id}?mesaj=pas_reluat", status_code=303)


@router.post("/{lid}/anuleaza", dependencies=[Depends(csrf_protect)])
def anuleaza(
    request: Request,
    u: PoateEdita,
    db: DbSession,
    lid: str,
    motiv: Annotated[str, Form(max_length=MOTIV_MAXIM)] = "",
) -> Response:
    """Anulează livrabilul (doar din stările în care tabelul de tranziții o permite), cu motiv și
    audit. Efectele
    lui încă neplecate se anulează odată cu el; cererea de aprobare în așteptare, la fel."""
    livrabil = _livrabil(db, lid)
    motiv_curat = _motiv(motiv)
    if motiv_curat is None:
        return _detaliu(
            request, u, db, livrabil, status=422, eroare="Scrie motivul anulării (cel puțin 3 caractere)."
        )
    stare_l = Stare(livrabil.stare)
    if not productie.este_permisa(stare_l, Stare.ANULAT):
        return _detaliu(
            request,
            u,
            db,
            livrabil,
            status=409,
            eroare=f"Din „{productie.ETICHETE[stare_l]}” livrabilul nu se mai anulează.",
        )
    try:
        productie.muta(
            db,
            livrabil.id,
            stare_l,
            Stare.ANULAT,
            componenta="om",
            utilizator_id=u.utilizator_id,
            motiv=motiv_curat,
        )
    except productie.TranzitieRefuzata as exc:
        return _detaliu(request, u, db, livrabil, status=409, eroare=str(exc))
    aprobari.anuleaza_cererea_in_asteptare(db, livrabil.id)
    for e in efecte.ale_livrabilului(db, livrabil.id):
        if e.stare in (
            StareEfect.IN_ASTEPTARE.value,
            StareEfect.ESUAT_TEMPORAR.value,
            StareEfect.ESUAT_DEFINITIV.value,
        ):
            efecte.anuleaza(db, e.id, motiv=f"livrabil anulat: {motiv_curat}", utilizator_id=u.utilizator_id)
    audit.record(
        db,
        "livrabil.anulat_de_om",
        obiect_tip="livrabil",
        obiect_id=livrabil.id,
        utilizator_id=u.utilizator_id,
        tenant_id=livrabil.tenant_id,
        detalii={"din": stare_l.value, "motiv": motiv_curat},
    )
    return RedirectResponse(f"/productie/{livrabil.id}?mesaj=anulat", status_code=303)
