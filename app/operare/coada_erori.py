"""Coada de erori (22.5): joburile care au eșuat, cu contextul complet, grupate pe cauză.

- Fiecare intrare spune ce job, ce pas, ce eroare și ce s-a încercat (`context`).
- Erorile cu aceeași cauză se grupează (`cauza`: amprentă din flux, pas, tipul și forma mesajului).
  O cauză nouă este un incident nou; o cauză care se repetă peste prag urcă la „major”.
- Nimic nu se șterge: o intrare se închide cu un motiv și cu cine a închis-o (`inchide`). Rolul
  aplicației nici nu are DELETE pe tabel.
- Mesajele de eroare sunt tăiate la 500 de caractere. Argumentele jobului sunt identificatori (regula
  din `motor.argumente`); rezultatele pașilor nu se citesc și nu se salvează.

Funcțiile primesc o sesiune: ecranul Alerte folosește sesiunea utilizatorului (RLS), watchdog-ul pe
cea de agenție.
"""

import hashlib
import re
import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ids import new_id
from app.operare import audit, evenimente
from app.operare.motor import DetaliiJob, PasJob, StareJob, reincercari_pas
from app.operare.tabele import IntrareEroare

LUNGIME_MESAJ = 500
PAS_TIMP_DEPASIT = "TimpDepasit"


class Severitate(StrEnum):
    CRITIC = "critic"
    MAJOR = "major"
    MINOR = "minor"
    INFORMATIV = "informativ"


RANG = {Severitate.CRITIC: 0, Severitate.MAJOR: 1, Severitate.MINOR: 2, Severitate.INFORMATIV: 3}
ETICHETE_SEVERITATE = {"critic": "Critic", "major": "Major", "minor": "Minor", "informativ": "Informativ"}


class Stare(StrEnum):
    NOUA = "noua"
    RELUATA = "reluata"
    INCHISA = "inchisa"


DESCHISE = (Stare.NOUA.value, Stare.RELUATA.value)
_NUMERE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d+", re.IGNORECASE)


def normalizeaza_mesaj(mesaj: str) -> str:
    """Forma mesajului fără identificatori și numere: două erori „aceeași cauză” au aceeași formă."""
    return " ".join(_NUMERE.sub("#", mesaj.lower()).split())[:200]


def amprenta_cauzei(flux: str, pas: str | None, eroare_tip: str, mesaj: str) -> str:
    brut = "|".join((flux, pas or "", eroare_tip, normalizeaza_mesaj(mesaj)))
    return hashlib.sha256(brut.encode()).hexdigest()[:16]


def clasifica(stare: StareJob, eroare_tip: str) -> Severitate:
    """Triere automată după 22.4: un job în coada de erori este „minor” (rezumat zilnic); căderile
    repetate ale workerului pe același job și erorile de autentificare ale conectorilor sunt „major”."""
    if stare is StareJob.EPUIZAT:
        return Severitate.MAJOR
    if eroare_tip == "EroareAutentificare":
        return Severitate.MAJOR
    return Severitate.MINOR


@dataclass(frozen=True)
class Rezultat:
    """Ce s-a întâmplat la înregistrarea unui job eșuat."""

    intrare: IntrareEroare
    nou: bool  # intrare creată acum (nu era deja în coadă)
    cauza_noua: bool  # prima intrare cu această cauză
    prag_atins: bool  # numărul de intrări deschise cu această cauză a ajuns exact la prag


def _tenant(db: Session, job: DetaliiJob) -> uuid.UUID | None:
    """Clientul jobului: primul argument sau `tenant_id=` dacă e un client existent (convenția fluxurilor)."""
    candidati = [job.kwargs.get("tenant_id"), *(job.argumente[:1])]
    for c in candidati:
        if not c:
            continue
        try:
            u = uuid.UUID(c)
        except ValueError:
            continue
        if db.execute(text("SELECT 1 FROM clienti WHERE id = :i"), {"i": u}).first():
            return u
    return None


def _ce_s_a_incercat(job: DetaliiJob, pas: PasJob | None, reluari: int) -> list[str]:
    incercat: list[str] = []
    if pas is not None and pas.eroare_tip:
        config = reincercari_pas(pas.nume)
        if pas.eroare_tip in ("EroareDefinitiva", "EroareAutentificare"):
            incercat.append("eroare definitivă: pasul nu se reîncearcă")
        elif config:
            incercat.append(f"pasul a fost reîncercat de până la {config} ori, cu pauză crescătoare")
        else:
            incercat.append("pasul nu are reîncercări configurate")
    if job.recuperari > 1:
        incercat.append(f"jobul a fost reluat de {job.recuperari - 1} ori după căderi ale workerului")
    if reluari:
        incercat.append(f"reluat de {reluari} ori din coada de erori")
    if job.bifurcat_din:
        incercat.append(f"este o reluare a jobului {job.bifurcat_din}")
    return incercat


def _context(
    job: DetaliiJob, pasi: list[PasJob], pas_esuat: PasJob | None, reluari: int
) -> dict[str, object]:
    return {
        "flux": job.nume,
        "argumente": job.argumente,
        "kwargs": job.kwargs,
        "coada": job.coada,
        "executor": job.executor,
        "versiune_joburi": job.versiune,
        "creat_la": job.creat_la.isoformat() if job.creat_la else None,
        "actualizat_la": job.actualizat_la.isoformat() if job.actualizat_la else None,
        "recuperari": job.recuperari,
        "bifurcat_din": job.bifurcat_din,
        "programare": job.programare,
        "pasi": [
            {
                "nr": p.nr,
                "nume": p.nume,
                "stare": "eroare" if p.esuat else "ok",
                "inceput": p.inceput.isoformat() if p.inceput else None,
                "sfarsit": p.sfarsit.isoformat() if p.sfarsit else None,
                "eroare": f"{p.eroare_tip}: {p.eroare_mesaj}"[:LUNGIME_MESAJ] if p.eroare_tip else None,
            }
            for p in pasi[:100]
        ],
        "ce_s_a_incercat": _ce_s_a_incercat(job, pas_esuat, reluari),
    }


def inregistreaza(
    db: Session,
    job: DetaliiJob,
    pasi: list[PasJob],
    *,
    prag_crestere: int,
    eroare_tip: str | None = None,
    eroare_mesaj: str | None = None,
    stare: Stare = Stare.NOUA,
    severitate: Severitate | None = None,
    reluari: int = 0,
) -> Rezultat | None:
    """Pune jobul în coada de erori sau actualizează intrarea lui. Întoarce `None` dacă intrarea există și a
    fost închisă (o decizie înregistrată nu se redeschide singură)."""
    pas_esuat = next((p for p in pasi if p.esuat), None)
    tip = eroare_tip or job.eroare_tip or (pas_esuat.eroare_tip if pas_esuat else None) or "Necunoscut"
    mesaj = (eroare_mesaj if eroare_mesaj is not None else job.eroare_mesaj or "")[:LUNGIME_MESAJ]
    pas = pas_esuat.nume if pas_esuat else None
    cauza = amprenta_cauzei(job.nume, pas, tip, mesaj)
    sev = severitate or clasifica(job.stare, tip)
    existent = db.execute(
        select(IntrareEroare).where(IntrareEroare.workflow_id == job.id).with_for_update()
    ).scalar_one_or_none()
    if existent is not None:
        if existent.stare == Stare.INCHISA.value:
            return None
        if existent.stare == Stare.RELUATA.value and stare is Stare.NOUA:
            existent.stare = Stare.NOUA.value  # a eșuat din nou după reluare
        existent.stare_job = job.stare.value
        existent.eroare_tip, existent.eroare_mesaj, existent.pas, existent.cauza = tip, mesaj, pas, cauza
        if RANG[Severitate(sev)] < RANG[Severitate(existent.severitate)]:
            existent.severitate = sev.value
        existent.reluari = max(existent.reluari, reluari)
        existent.context = _context(job, pasi, pas_esuat, existent.reluari)
        existent.actualizat_la = func.now()
        db.flush()
        return Rezultat(existent, nou=False, cauza_noua=False, prag_atins=False)
    cauza_noua = (
        db.execute(
            select(func.count()).select_from(IntrareEroare).where(IntrareEroare.cauza == cauza)
        ).scalar_one()
        == 0
    )
    intrare = IntrareEroare(
        id=new_id(),
        tenant_id=_tenant(db, job),
        workflow_id=job.id,
        flux=job.nume,
        pas=pas,
        stare_job=job.stare.value,
        coada=job.coada,
        executor_id=job.executor,
        eroare_tip=tip,
        eroare_mesaj=mesaj,
        cauza=cauza,
        severitate=sev.value,
        stare=stare.value,
        reluari=reluari,
        context=_context(job, pasi, pas_esuat, reluari),
    )
    try:
        with db.begin_nested():
            db.add(intrare)
            db.flush()
    except IntegrityError:  # alt watchdog a înregistrat-o între timp
        return None
    deschise_cu_cauza = db.execute(
        select(func.count())
        .select_from(IntrareEroare)
        .where(IntrareEroare.cauza == cauza, IntrareEroare.stare.in_(DESCHISE))
    ).scalar_one()
    prag_atins = deschise_cu_cauza == prag_crestere
    if prag_atins:  # coadă care crește: toată cauza urcă la major
        for i in db.execute(
            select(IntrareEroare).where(
                IntrareEroare.cauza == cauza,
                IntrareEroare.stare.in_(DESCHISE),
                IntrareEroare.severitate.in_((Severitate.MINOR.value, Severitate.INFORMATIV.value)),
            )
        ).scalars():
            i.severitate = Severitate.MAJOR.value
    evenimente.emite(
        db,
        "job.in_coada_de_erori",
        sursa="watchdog",
        obiect_tip="job",
        obiect_id=job.id,
        tenant_id=intrare.tenant_id,
        date={"flux": job.nume, "pas": pas, "cauza": cauza, "severitate": intrare.severitate},
    )
    return Rezultat(intrare, nou=True, cauza_noua=cauza_noua, prag_atins=prag_atins)


# --- citire, pentru ecranul Alerte --------------------------------------------------------------------------


@dataclass(frozen=True)
class Grup:
    cauza: str
    flux: str
    pas: str | None
    eroare_tip: str
    severitate: str
    intrari: int
    ultima: IntrareEroare
    recente: list[IntrareEroare]


def lista(db: Session, *, doar_deschise: bool = True, limita: int = 500) -> list[IntrareEroare]:
    q = select(IntrareEroare).order_by(IntrareEroare.creat_la.desc()).limit(limita)
    if doar_deschise:
        q = q.where(IntrareEroare.stare.in_(DESCHISE))
    return list(db.execute(q).scalars())


def grupeaza(intrari: list[IntrareEroare]) -> list[Grup]:
    """Grupează pe cauză; cele mai grave primele, apoi cele mai recente."""
    grupuri: dict[str, list[IntrareEroare]] = {}
    for i in intrari:
        grupuri.setdefault(i.cauza, []).append(i)
    rezultat = [
        Grup(
            cauza=cauza,
            flux=randuri[0].flux,
            pas=randuri[0].pas,
            eroare_tip=randuri[0].eroare_tip,
            severitate=min((r.severitate for r in randuri), key=lambda s: RANG[Severitate(s)]),
            intrari=len(randuri),
            ultima=max(randuri, key=lambda r: r.creat_la),
            recente=sorted(randuri, key=lambda r: r.creat_la, reverse=True)[:5],
        )
        for cauza, randuri in grupuri.items()
    ]
    return sorted(rezultat, key=lambda g: (RANG[Severitate(g.severitate)], -g.ultima.creat_la.timestamp()))


def gaseste(db: Session, id_intrare: uuid.UUID) -> IntrareEroare | None:
    return db.get(IntrareEroare, id_intrare)


def numar_deschise(db: Session) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(IntrareEroare).where(IntrareEroare.stare.in_(DESCHISE))
        ).scalar_one()
    )


def din_aceeasi_cauza(db: Session, intrare: IntrareEroare, limita: int = 20) -> list[IntrareEroare]:
    return list(
        db.execute(
            select(IntrareEroare)
            .where(IntrareEroare.cauza == intrare.cauza, IntrareEroare.id != intrare.id)
            .order_by(IntrareEroare.creat_la.desc())
            .limit(limita)
        ).scalars()
    )


# --- decizii (cu audit) -------------------------------------------------------------------------------------


def marcheaza_reluata(
    db: Session, intrare: IntrareEroare, *, reluat_ca: str | None, utilizator_id: uuid.UUID | None
) -> None:
    """Marchează intrarea ca reluată. `reluat_ca`: identificatorul jobului nou (bifurcare), sau `None` dacă
    s-a reluat același job (anulat/epuizat)."""
    intrare.stare = Stare.RELUATA.value
    intrare.reluari += 1
    intrare.reluat_ca = reluat_ca
    intrare.actualizat_la = func.now()
    db.flush()
    audit.record(
        db,
        "alerte.reia",
        obiect_tip="coada_erori",
        obiect_id=intrare.id,
        utilizator_id=utilizator_id,
        tenant_id=intrare.tenant_id,
        actor_tip=None if utilizator_id else "sistem",
        detalii={
            "job": intrare.workflow_id,
            "continua_ca": reluat_ca or intrare.workflow_id,
            "flux": intrare.flux,
        },
    )


def inchide(db: Session, intrare: IntrareEroare, *, motiv: str, utilizator_id: uuid.UUID | None) -> None:
    """Închide intrarea cu un motiv (decizie înregistrată). Nu o șterge."""
    motiv = motiv.strip()[:300]
    if not motiv:
        raise ValueError("închiderea cere un motiv")
    intrare.stare = Stare.INCHISA.value
    intrare.inchis_la = func.now()
    intrare.inchis_de = utilizator_id
    intrare.motiv_inchidere = motiv
    intrare.actualizat_la = func.now()
    db.flush()
    audit.record(
        db,
        "alerte.inchide",
        obiect_tip="coada_erori",
        obiect_id=intrare.id,
        utilizator_id=utilizator_id,
        tenant_id=intrare.tenant_id,
        actor_tip=None if utilizator_id else "sistem",
        detalii={"job": intrare.workflow_id, "motiv": motiv, "flux": intrare.flux},
    )
