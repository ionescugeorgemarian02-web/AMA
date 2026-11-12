"""Învelișul bibliotecii de workflow-uri (ADR-03): singurul modul din aplicație care importă `dbos`.

Ce expune (prin `app.operare.motor`):
- `flux` și `pas`: decoratorii fluxurilor durabile și ai pașilor lor (rezultatul fiecărui pas se
  salvează în bază;
  după o cădere, fluxul reia de la primul pas nesalvat);
- `trimite`: pune un flux în coadă (procesul web doar face asta, printr-un client subțire fără executor);
- `stare_flux`, `asteapta_flux`: citirea stării unui job.

Executorul (cel care rulează fluxurile) pornește doar în procesul `worker` (vezi `ciclu`).
"""

import datetime as dt
import functools
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ParamSpec, TypeVar

from dbos import DBOS, DBOSClient, EnqueueOptions

from app.config import get_settings
from app.operare.motor import argumente
from app.operare.motor.cozi import (
    NUME_COADA,
    Coada,
    DefinitieCoada,
    Prioritate,
    calculeaza_prioritate,
    definitii_standard,
)
from app.operare.motor.erori import EroareDefinitiva

NUME_APLICATIE = "ama"
RECUPERARI_IMPLICIT = 5  # de câte ori e reluat un flux care strică workerul înainte să ajungă la oameni
CHEIE_VALIDA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,159}$")
ATRIBUT_NUME = "__ama_flux__"

P = ParamSpec("P")
R = TypeVar("R")

_lock = threading.RLock()
_client: DBOSClient | None = None
_cozi_extra: dict[str, DefinitieCoada] = {}
_timp_maxim: dict[str, float | None] = {}  # numele fluxului -> timpul maxim fără progres (None = implicit)
_reincercari: dict[str, int] = {}  # numele pasului -> câte reîncercări are configurate


class StareJob(StrEnum):
    """Starea unui job, pe înțelesul aplicației (cuvinte din `docs/07`, nu din bibliotecă)."""

    AMANAT = "amanat"  # DELAYED: are un moment de pornire în viitor (slot)
    IN_COADA = "in_coada"  # ENQUEUED
    IN_LUCRU = "in_lucru"  # PENDING
    TERMINAT = "terminat"  # SUCCESS
    ESUAT = "esuat"  # ERROR: a aruncat o eroare (după reîncercările pașilor)
    ANULAT = "anulat"  # CANCELLED
    EPUIZAT = "epuizat"  # MAX_RECOVERY_ATTEMPTS_EXCEEDED: a căzut de prea multe ori împreună cu workerul
    SUSPENDAT = "suspendat"  # SUSPENDED

    @property
    def final(self) -> bool:
        return self in (StareJob.TERMINAT, StareJob.ESUAT, StareJob.ANULAT, StareJob.EPUIZAT)


_STARI = {
    "DELAYED": StareJob.AMANAT,
    "ENQUEUED": StareJob.IN_COADA,
    "PENDING": StareJob.IN_LUCRU,
    "SUCCESS": StareJob.TERMINAT,
    "ERROR": StareJob.ESUAT,
    "CANCELLED": StareJob.ANULAT,
    "MAX_RECOVERY_ATTEMPTS_EXCEEDED": StareJob.EPUIZAT,
    "SUSPENDED": StareJob.SUSPENDAT,
}


def stare_din_biblioteca(valoare: str) -> StareJob:
    return _STARI[valoare]


def stare_biblioteca(stare: StareJob) -> str:
    return next(k for k, v in _STARI.items() if v is stare)


@dataclass(frozen=True)
class StareFlux:
    id: str
    nume: str
    stare: StareJob
    coada: str | None
    eroare: str | None
    executor: str | None
    creat_la: dt.datetime | None
    actualizat_la: dt.datetime | None


def _moment(ms: int | None) -> dt.datetime | None:
    return None if ms is None else dt.datetime.fromtimestamp(ms / 1000, dt.UTC)


# --- decoratori --------------------------------------------------------------------------------------


def _nume(nume: str | None, fn: Callable[..., Any]) -> str:
    return nume or f"{fn.__module__}.{fn.__qualname__}"


def flux(
    nume: str | None = None,
    *,
    recuperari_max: int = RECUPERARI_IMPLICIT,
    timp_maxim_sec: float | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Declară un flux durabil. Numele (stabil, scris în bază) e implicit `modul.funcție`.

    Primește doar identificatori (vezi `argumente`), `tenant_id` în frunte dacă ating date de client.
    Cod nedeterminist (ora, aleatoriu, citiri din bază) se pune în pași, nu în corpul fluxului: la reluare,
    corpul se reexecută, iar pașii deja salvați întorc rezultatul lor.
    `recuperari_max`: de câte ori e reluat după căderi ale workerului; peste, ajunge `EPUIZAT` (coada
    de erori). `timp_maxim_sec`: cât poate sta fără niciun pas încheiat înainte ca watchdog-ul să-l
    considere blocat (implicit `AMA_JOB_TIMP_MAXIM_SEC`).
    """

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        n = _nume(nume, fn)

        @functools.wraps(fn)
        def interior(*args: P.args, **kwargs: P.kwargs) -> R:
            argumente.verifica(n, args, kwargs)
            return fn(*args, **kwargs)

        invelit = DBOS.workflow(name=n, max_recovery_attempts=recuperari_max)(interior)
        setattr(invelit, ATRIBUT_NUME, n)
        _timp_maxim[n] = timp_maxim_sec
        return invelit

    return decorator


def timp_maxim_flux(nume: str) -> float:
    """Timpul maxim fără progres al fluxului `nume` (cel declarat sau cel din configurare)."""
    declarat = _timp_maxim.get(nume)
    return declarat if declarat is not None else float(get_settings().job_timp_maxim_sec)


def reincercari_pas(nume: str) -> int | None:
    """Câte reîncercări are configurate pasul `nume` (None dacă acest proces nu îl cunoaște)."""
    return _reincercari.get(nume)


def nume_flux(fn: Callable[..., Any]) -> str:
    """Numele sub care un flux este scris în bază; `TypeError` dacă funcția nu e decorată cu `@flux`."""
    n = getattr(fn, ATRIBUT_NUME, None)
    if not isinstance(n, str):
        raise TypeError(f"{getattr(fn, '__qualname__', fn)!r} nu este un flux (lipsește @flux)")
    return n


def pas(
    nume: str | None = None, *, reincercari: int = 0, pauza_sec: float = 1.0, factor: float = 2.0
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Declară un pas al unui flux. Rezultatul se salvează; la reluare nu se mai execută.

    `reincercari`: câte reîncercări după prima încercare, cu pauză crescătoare (`pauza_sec`, × `factor`):
    3 reîncercări cu 1 s și factor 2 înseamnă pauze de 1, 2 și 4 secunde (7.5, erori de server). Nu se
    reîncearcă
    `EroareDefinitiva` (inclusiv `EroareAutentificare`). Garanția este „cel puțin o dată": un pas
    întrerupt de o
    cădere se execută din nou, deci efectele externe au nevoie de cheie de idempotență (F2.5).
    """
    if reincercari < 0:
        raise ValueError("reincercari ≥ 0")

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        n = _nume(nume, fn)

        @functools.wraps(fn)
        def interior(*args: P.args, **kwargs: P.kwargs) -> R:
            argumente.verifica(n, args, kwargs)
            return fn(*args, **kwargs)

        _reincercari[n] = reincercari
        return DBOS.step(
            name=n,
            retries_allowed=reincercari > 0,
            max_attempts=reincercari + 1,
            interval_seconds=pauza_sec,
            backoff_rate=factor,
            should_retry=lambda e: not isinstance(e, EroareDefinitiva),
        )(interior)

    return decorator


_executor_pornit = False


def pornit() -> bool:
    return _executor_pornit


def seteaza_pornit(valoare: bool) -> None:
    global _executor_pornit
    _executor_pornit = valoare


def inregistreaza_coada(d: DefinitieCoada) -> None:
    """Scrie configurarea unei cozi în bază. Workerul e proprietarul ei: la fiecare pornire se aplică valorile
    din configurare (`always_update`), deci schimbarea unei limite cere doar repornirea workerului."""
    limiter = {"limit": d.cereri, "period": d.perioada_sec} if d.cereri is not None else None
    DBOS.register_queue(
        d.nume,
        global_concurrency=d.paralel_global,
        worker_concurrency=d.paralel_worker,
        limiter=limiter,  # type: ignore[arg-type]
        polling_interval_sec=d.polling_sec,
        on_conflict="always_update",
    )


def definitii_cozi() -> list[DefinitieCoada]:
    """Cozile fixe din 7.5 (limitele din configurare), apoi cele declarate (furnizori, platforme)."""
    return [*definitii_standard(get_settings()), *cozi_extra()]


def preinregistreaza_cozi() -> None:
    """Scrie configurarea cozilor ÎNAINTE de lansarea bibliotecii, prin clientul subțire.

    Firele cozilor pornesc la lansare cu ce găsesc în bază și apucă să scoată joburi cu limitele vechi până la
    următoarea lor sondare. Cu configurarea scrisă dinainte, prima sondare vede deja limitele noi (de exemplu
    nu pornesc trei joburi grele după ce numărul de culoare a fost scăzut la unu)."""
    for d in definitii_cozi():
        limiter = {"limit": d.cereri, "period": d.perioada_sec} if d.cereri is not None else None
        client().register_queue(
            d.nume,
            global_concurrency=d.paralel_global,
            worker_concurrency=d.paralel_worker,
            limiter=limiter,  # type: ignore[arg-type]
            polling_interval_sec=d.polling_sec,
            on_conflict="always_update",
        )


def inregistreaza_cozi() -> None:
    """Înregistrarea din interiorul bibliotecii lansate (idempotentă după `preinregistreaza_cozi`)."""
    for d in definitii_cozi():
        inregistreaza_coada(d)


def declara_coada(definitie: DefinitieCoada) -> None:
    """Adaugă o coadă (de furnizor sau de platformă) la cele standard; se înregistrează la pornirea
    workerului, sau pe loc dacă executorul rulează deja. Numele fixe din 7.5 nu se pot redeclara."""
    if definitie.nume in {c.value for c in Coada}:
        raise ValueError(f"coada {definitie.nume!r} este una dintre cele fixe")
    with _lock:
        _cozi_extra[definitie.nume] = definitie
        if pornit():
            inregistreaza_coada(definitie)


def cozi_extra() -> list[DefinitieCoada]:
    with _lock:
        return list(_cozi_extra.values())


# --- clientul (procesul web) ----------------------------------------------------------------------------


def client() -> DBOSClient:
    """Clientul subțire spre tabelele bibliotecii: pune în coadă și citește; fără executor."""
    global _client
    with _lock:
        if _client is None:
            s = get_settings()
            _client = DBOSClient(
                system_database_url=s.database_url,
                dbos_system_schema=s.motor_schema,
                application_name=NUME_APLICATIE,
                system_database_pool_size=3,
                lazy=True,  # nu se conectează până nu e folosit: aplicația web pornește și fără motor
                retry_connection_errors=False,  # baza căzută = eroare imediată, nu cerere blocată
            )
        return _client


def inchide_client() -> None:
    global _client
    with _lock:
        if _client is not None:
            _client.destroy()
            _client = None


def trimite(
    fluxul: Callable[..., Any],
    *args: Any,
    coada: Coada | str = Coada.IO,
    prioritate: Prioritate = Prioritate.P1,
    termen: dt.datetime | None = None,
    cheie: str | None = None,
    la: dt.datetime | None = None,
    kwargs: dict[str, Any] | None = None,
) -> str:
    """Pune un flux în coadă și întoarce identificatorul jobului. Nu pornește niciun executor.

    - `coada`: una dintre cele patru fixe din 7.5 (`Coada`) sau o coadă declarată (`declara_coada`:
      furnizor, platformă). `prioritate` (P0–P3) și `termen`: în aceeași clasă câștigă termenul cel mai
      apropiat (vezi `cozi`).
    - `cheie`: identificator de idempotență; aceeași cheie de două ori = același job (nu se dublează).
      Folosește una derivată din lucrul de făcut (de exemplu `livrabil:<id>:v3`), mai ales dacă `trimite`
      e apelat dintr-un pas.
    - `la`: nu porni înainte de acest moment (slot); jobul așteaptă în bază și supraviețuiește repornirilor.
    """
    nume = nume_flux(fluxul)
    nume_coada = coada.value if isinstance(coada, Coada) else coada
    if not NUME_COADA.match(nume_coada):
        raise ValueError(f"nume de coadă nepermis: {nume_coada!r}")
    if cheie is not None and not CHEIE_VALIDA.match(cheie):
        raise ValueError("cheie de idempotență nepermisă (litere, cifre, `._:@/-`, maxim 160)")
    kw = kwargs or {}
    argumente.verifica(nume, args, kw)
    s = get_settings()
    optiuni: EnqueueOptions = {
        "workflow_name": nume,
        "queue_name": nume_coada,
        "priority": calculeaza_prioritate(prioritate, termen),
        "app_version": s.motor_versiune,
        "application_name": NUME_APLICATIE,
        # Anularea scoate jobul din coadă; reluarea trebuie să-l pună la loc în coada lui (vezi `inspectie`).
        "attributes": {"coada": nume_coada},
    }
    if cheie is not None:
        optiuni["workflow_id"] = cheie
    if la is not None:
        if la.tzinfo is None:
            raise ValueError("`la` trebuie să aibă fus orar")
        optiuni["delay_seconds"] = max(0.0, (la - dt.datetime.now(dt.UTC)).total_seconds())
    return client().enqueue(optiuni, *args, **kw).get_workflow_id()


def stare_flux(id_job: str) -> StareFlux | None:
    randuri = client().list_workflows(workflow_ids=[id_job], load_input=False, load_output=True)
    if not randuri:
        return None
    w = randuri[0]
    return StareFlux(
        id=w.workflow_id,
        nume=w.name,
        stare=stare_din_biblioteca(w.status),
        coada=w.queue_name,
        eroare=None if w.error is None else f"{type(w.error).__name__}: {w.error}"[:500],
        executor=w.executor_id,
        creat_la=_moment(w.created_at),
        actualizat_la=_moment(w.updated_at),
    )


def asteapta_flux(id_job: str, *, timeout_sec: float = 30.0, pauza_sec: float = 0.05) -> StareFlux:
    """Așteaptă starea finală (terminat, eșuat, anulat, epuizat). `TimeoutError` dacă nu vine la timp."""
    limita = time.monotonic() + timeout_sec
    while True:
        stare = stare_flux(id_job)
        if stare is not None and stare.stare.final:
            return stare
        if time.monotonic() > limita:
            raise TimeoutError(f"jobul {id_job} nu s-a încheiat în {timeout_sec} s (stare: {stare})")
        time.sleep(pauza_sec)
