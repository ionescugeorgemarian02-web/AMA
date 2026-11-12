"""Inspecția și acțiunile asupra joburilor, pentru watchdog și pentru ecranul Alerte (F2.7).

Totul trece prin clientul subțire (nu cere executor): se poate apela și din procesul web. Rezultatele sunt
obiecte simple ale proiectului, fără tipuri ale bibliotecii. Argumentele joburilor se întorc ca texte scurte
(regula din `argumente`: sunt doar identificatori); rezultatele pașilor nu se citesc niciodată.
"""

import datetime as dt
from dataclasses import dataclass, field

from app.config import get_settings
from app.operare.motor.erori import EroareMotor
from app.operare.motor.executie import (
    StareJob,
    client,
    stare_biblioteca,
    stare_din_biblioteca,
)

LIMITA_TEXT = 200


class JobNereluabil(EroareMotor):
    """Jobul nu se află într-o stare din care poate fi reluat (încă rulează, s-a terminat cu bine …)."""


@dataclass(frozen=True)
class PasJob:
    nr: int
    nume: str
    inceput: dt.datetime | None
    sfarsit: dt.datetime | None
    eroare_tip: str | None
    eroare_mesaj: str | None

    @property
    def esuat(self) -> bool:
        return self.eroare_tip is not None

    @property
    def sfarsit_sau_inceput(self) -> dt.datetime | None:
        return self.sfarsit or self.inceput


@dataclass(frozen=True)
class DetaliiJob:
    id: str
    nume: str
    stare: StareJob
    coada: str | None
    executor: str | None
    versiune: str | None
    creat_la: dt.datetime | None
    actualizat_la: dt.datetime | None
    scos_din_coada_la: dt.datetime | None
    recuperari: int
    bifurcat_din: str | None
    programare: str | None
    argumente: list[str] = field(default_factory=list)
    kwargs: dict[str, str] = field(default_factory=dict)
    eroare_tip: str | None = None
    eroare_mesaj: str | None = None


def _moment(ms: int | None) -> dt.datetime | None:
    return None if ms is None else dt.datetime.fromtimestamp(ms / 1000, dt.UTC)


def _text(valoare: object) -> str:
    return str(valoare)[:LIMITA_TEXT]


def _detalii(w: object) -> DetaliiJob:
    entrare = getattr(w, "input", None) or {}
    args = entrare.get("args", ()) if isinstance(entrare, dict) else ()
    kwargs = entrare.get("kwargs", {}) if isinstance(entrare, dict) else {}
    eroare = getattr(w, "error", None)
    return DetaliiJob(
        id=w.workflow_id,  # type: ignore[attr-defined]
        nume=w.name,  # type: ignore[attr-defined]
        stare=stare_din_biblioteca(w.status),  # type: ignore[attr-defined]
        # Anularea scoate jobul din coadă (biblioteca pune `queue_name` NULL): coada se păstrează în atribute.
        coada=w.queue_name or (getattr(w, "attributes", None) or {}).get("coada"),  # type: ignore[attr-defined]
        executor=w.executor_id,  # type: ignore[attr-defined]
        versiune=w.app_version,  # type: ignore[attr-defined]
        creat_la=_moment(w.created_at),  # type: ignore[attr-defined]
        actualizat_la=_moment(w.updated_at),  # type: ignore[attr-defined]
        scos_din_coada_la=_moment(w.dequeued_at),  # type: ignore[attr-defined]
        recuperari=int(getattr(w, "recovery_attempts", 0) or 0),
        bifurcat_din=w.forked_from,  # type: ignore[attr-defined]
        programare=w.schedule_name,  # type: ignore[attr-defined]
        argumente=[_text(a) for a in list(args)[:10]],
        kwargs={_text(k): _text(v) for k, v in list(kwargs.items())[:10]},
        eroare_tip=None if eroare is None else type(eroare).__name__,
        eroare_mesaj=None if eroare is None else _text(eroare),
    )


def detalii_job(id_job: str) -> DetaliiJob | None:
    randuri = client().list_workflows(workflow_ids=[id_job], load_output=True)
    return _detalii(randuri[0]) if randuri else None


def joburi_in_stare(stari: list[StareJob], limita: int = 300) -> list[DetaliiJob]:
    """Cele mai noi `limita` joburi din aceste stări."""
    randuri = client().list_workflows(
        status=[stare_biblioteca(s) for s in stari], sort_desc=True, limit=limita, load_output=True
    )
    return [_detalii(w) for w in randuri]


def joburi_esuate(limita: int = 300) -> list[DetaliiJob]:
    return joburi_in_stare([StareJob.ESUAT, StareJob.EPUIZAT], limita)


def joburi_in_lucru(limita: int = 300) -> list[DetaliiJob]:
    return joburi_in_stare([StareJob.IN_LUCRU], limita)


def joburi_pentru(valori: list[str], limita: int = 500) -> list[DetaliiJob]:
    """Joburile (cele mai noi `limita`, de orice stare) ai căror argumente conțin vreuna dintre `valori`
    (identificatori: livrabil, efect). Argumentele fluxurilor sunt doar identificatori (`argumente`), deci o
    potrivire exactă pe ei găsește jobul unui lucru anume. Apelează-o doar după ce ai verificat că lucrul e
    vizibil utilizatorului: tabelele motorului nu au izolare pe client."""
    cautate = set(valori)
    randuri = client().list_workflows(sort_desc=True, limit=limita, load_output=True)
    gasite = []
    for w in randuri:
        j = _detalii(w)
        if cautate & (set(j.argumente) | set(j.kwargs.values())):
            gasite.append(j)
    return gasite


@dataclass(frozen=True)
class AdancimeCoada:
    nume: str
    in_coada: int  # așteaptă un culoar
    in_lucru: int  # rulează acum


def adancime_cozi(limita: int = 5000) -> list[AdancimeCoada]:
    """Câte joburi așteaptă și câte rulează, pe fiecare coadă (doar cozile cu joburi apar)."""
    randuri = client().list_workflows(
        status=["ENQUEUED", "PENDING"], queues_only=True, load_input=False, load_output=False, limit=limita
    )
    contor: dict[str, list[int]] = {}
    for w in randuri:
        c = contor.setdefault(w.queue_name or "?", [0, 0])
        c[0 if w.status == "ENQUEUED" else 1] += 1
    return [AdancimeCoada(n, v[0], v[1]) for n, v in sorted(contor.items())]


def pasi_job(id_job: str) -> list[PasJob]:
    pasi = client().list_workflow_steps(id_job, load_output=True)  # eroarea vine odată cu rezultatul
    return [
        PasJob(
            nr=p["function_id"],
            nume=p["function_name"],
            inceput=_moment(p.get("started_at_epoch_ms")),
            sfarsit=_moment(p.get("completed_at_epoch_ms")),
            eroare_tip=None if p.get("error") is None else type(p["error"]).__name__,
            eroare_mesaj=None if p.get("error") is None else _text(p["error"]),
        )
        for p in pasi
    ]


def ultimul_progres(job: DetaliiJob, pasi: list[PasJob]) -> dt.datetime | None:
    """Ultimul semn de progres: cel mai târziu dintre intrarea în lucru, ultima actualizare și ultimul pas."""
    momente = [m for m in (job.scos_din_coada_la, job.actualizat_la, job.creat_la) if m is not None]
    momente += [p.sfarsit for p in pasi if p.sfarsit is not None]
    return max(momente) if momente else None


def _coada_originala(job: DetaliiJob) -> str:
    return job.coada or "io"


def pas_de_reluare(pasi: list[PasJob]) -> int:
    """Pasul de la care se reia un job eșuat: primul pas cu eroare; altfel după ultimul pas încheiat."""
    for p in pasi:
        if p.esuat:
            return p.nr
    return (max(p.nr for p in pasi) + 1) if pasi else 0


def reia_job(id_job: str, de_la_pas: int | None = None) -> str:
    """Reia un job și întoarce identificatorul celui care continuă.

    - anulat sau epuizat (căderi repetate): același job, din ultimul pas salvat, în coada lui;
    - eșuat (a aruncat o eroare): biblioteca nu reia un job `ERROR`, deci se face o *bifurcare*: un job
      nou, care copiază pașii dinaintea celui eșuat (rezultatele lor nu se recalculează) și reia de la
      `de_la_pas` (implicit primul pas eșuat).
    Orice altă stare aruncă `JobNereluabil`."""
    job = detalii_job(id_job)
    if job is None:
        raise JobNereluabil("jobul nu mai există în baza motorului")
    if job.stare in (StareJob.ANULAT, StareJob.EPUIZAT):
        client().resume_workflow(id_job, queue_name=_coada_originala(job))
        return id_job
    if job.stare is StareJob.ESUAT:
        pas = de_la_pas if de_la_pas is not None else pas_de_reluare(pasi_job(id_job))
        nou = client().fork_workflow(
            id_job,
            pas,
            application_version=get_settings().motor_versiune,
            queue_name=_coada_originala(job),
        )
        return nou.get_workflow_id()
    raise JobNereluabil(
        f"jobul este în starea „{job.stare.value}”; se reia doar un job eșuat, anulat sau epuizat"
    )


def anuleaza_job(id_job: str) -> None:
    client().cancel_workflow(id_job)


def opreste_si_reia(id_job: str) -> None:
    """Pentru un job blocat: îl anulează și îl pune la loc în coada lui, din ultimul pas salvat."""
    job = detalii_job(id_job)
    if job is None:
        raise JobNereluabil("jobul nu mai există în baza motorului")
    client().cancel_workflow(id_job)
    client().resume_workflow(id_job, queue_name=_coada_originala(job))


__all__ = [
    "AdancimeCoada",
    "DetaliiJob",
    "JobNereluabil",
    "PasJob",
    "adancime_cozi",
    "anuleaza_job",
    "detalii_job",
    "joburi_esuate",
    "joburi_in_lucru",
    "joburi_in_stare",
    "joburi_pentru",
    "opreste_si_reia",
    "pas_de_reluare",
    "pasi_job",
    "reia_job",
    "ultimul_progres",
]
