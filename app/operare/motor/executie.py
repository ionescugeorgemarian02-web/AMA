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
from app.operare.motor.erori import EroareDefinitiva

NUME_APLICATIE = "ama"
RECUPERARI_IMPLICIT = 5  # de câte ori e reluat un flux care strică workerul înainte să ajungă la oameni
NUME_COADA = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
COADA_IMPLICITA = "io"
CHEIE_VALIDA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,159}$")
ATRIBUT_NUME = "__ama_flux__"

P = ParamSpec("P")
R = TypeVar("R")

_lock = threading.RLock()
_client: DBOSClient | None = None


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
    nume: str | None = None, *, recuperari_max: int = RECUPERARI_IMPLICIT
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Declară un flux durabil. Numele (stabil, scris în bază) e implicit `modul.funcție`.

    Primește doar identificatori (vezi `argumente`), `tenant_id` în frunte dacă ating date de client.
    Cod nedeterminist (ora, aleatoriu, citiri din bază) se pune în pași, nu în corpul fluxului: la reluare,
    corpul se reexecută, iar pașii deja salvați întorc rezultatul lor.
    `recuperari_max`: de câte ori e reluat după căderi ale workerului; peste, ajunge `EPUIZAT` (coada
    de erori).
    """

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        n = _nume(nume, fn)

        @functools.wraps(fn)
        def interior(*args: P.args, **kwargs: P.kwargs) -> R:
            argumente.verifica(n, args, kwargs)
            return fn(*args, **kwargs)

        invelit = DBOS.workflow(name=n, max_recovery_attempts=recuperari_max)(interior)
        setattr(invelit, ATRIBUT_NUME, n)
        return invelit

    return decorator


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


def inregistreaza_cozi() -> None:
    """Cozile executorului. În F2.1 doar `io`; setul din 7.5 (urgent, greu, învățare) vine în F2.2."""
    s = get_settings()
    DBOS.register_queue(
        COADA_IMPLICITA,
        global_concurrency=s.io_paralel,
        worker_concurrency=s.io_paralel,
        polling_interval_sec=s.motor_polling_sec,
        on_conflict="always_update",
    )


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
    coada: str = COADA_IMPLICITA,
    cheie: str | None = None,
    la: dt.datetime | None = None,
    kwargs: dict[str, Any] | None = None,
) -> str:
    """Pune un flux în coadă și întoarce identificatorul jobului. Nu pornește niciun executor.

    - `coada`: numele cozii (cozile și prioritățile din 7.5 vin în F2.2).
    - `cheie`: identificator de idempotență; aceeași cheie de două ori = același job (nu se dublează).
      Folosește
      una derivată din lucrul de făcut (de exemplu `livrabil:<id>:v3`), mai ales dacă `trimite` e
      apelat dintr-un pas.
    - `la`: nu porni înainte de acest moment (slot); jobul așteaptă în bază și supraviețuiește repornirilor.
    """
    nume = nume_flux(fluxul)
    if not NUME_COADA.match(coada):
        raise ValueError(f"nume de coadă nepermis: {coada!r}")
    if cheie is not None and not CHEIE_VALIDA.match(cheie):
        raise ValueError("cheie de idempotență nepermisă (litere, cifre, `._:@/-`, maxim 160)")
    kw = kwargs or {}
    argumente.verifica(nume, args, kw)
    s = get_settings()
    optiuni: EnqueueOptions = {
        "workflow_name": nume,
        "queue_name": coada,
        "app_version": s.motor_versiune,
        "application_name": NUME_APLICATIE,
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
