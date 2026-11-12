"""Planificatorul de timp (B4, F2.6): joburi recurente și sloturi.

**Recurente.** Un flux cu semnătura `(moment: datetime, context: dict | None)`, rulat după un cron în
fusul orar al afacerii (implicit `Europe/Bucharest`, cu trecerea la ora de vară). Programările se
declară în cod (`programeaza_recurent`) și se scriu în bază la pornirea workerului
(`aplica_programari`, idempotent: nu resetează pauza și nici ultima declanșare). Se declanșează în
procesul `worker`, cel mult o dată pe tic, chiar cu mai mulți workeri (biblioteca ține o încuietoare
în bază: ține un singur proces, iar ceilalți preiau dacă el cade).

Cron-ul este cel obișnuit, cu 5 câmpuri (minut, oră, zi, lună, zi din săptămână): *rulează la minut*,
adică la secunda 0. Pentru probe se acceptă și 6 câmpuri, cu secundele în față.

**Sloturi.** O singură rulare la un moment dat (de exemplu slotul de publicare de la 18:30):
`programeaza_slot`. Jobul așteaptă în bază (`amanat`) și supraviețuiește repornirilor; dacă momentul
trece cât workerul e oprit, pornește imediat ce workerul revine. Cheia face slotul idempotent (a doua
programare cu aceeași cheie nu dublează).

Limite spuse deschis: precizia este cea a sondării (`AMA_PROGRAMARE_POLLING_SEC` pentru recurente,
`AMA_MOTOR_POLLING_SEC` pentru sloturi). Biblioteca pune rulările programate pe prioritatea cea mai
mare a cozii (0): fluxul programat trebuie să fie mic și să trimită munca reală cu `trimite`, cu
prioritatea ei.
"""

import datetime as dt
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dbos import ClientScheduleInput

from app.operare.motor import argumente
from app.operare.motor.cozi import NUME_COADA, Coada, Prioritate
from app.operare.motor.executie import (
    StareJob,
    client,
    nume_flux,
    stare_biblioteca,
    stare_din_biblioteca,
    trimite,
)

FUS_IMPLICIT = "Europe/Bucharest"
NUME_PROGRAMARE = re.compile(r"^[a-z][a-z0-9_.-]{1,80}$")
_registru: dict[str, "Programare"] = {}


class ProgramareInvalida(ValueError):
    """Cron, nume, fus orar sau context nepermis."""


@dataclass(frozen=True)
class Programare:
    nume: str
    cron: str  # forma completă (6 câmpuri, secundele în față), cum o ține biblioteca
    flux: str  # numele fluxului
    context: dict[str, Any] | None
    fus_orar: str
    coada: str
    recupereaza_ratate: bool


@dataclass(frozen=True)
class InfoProgramare:
    nume: str
    cron: str
    flux: str
    stare: str  # "activa" | "pe_pauza"
    fus_orar: str | None
    coada: str | None
    ultima_declansare: dt.datetime | None


@dataclass(frozen=True)
class Slot:
    cheie: str
    flux: str
    coada: str | None
    la: dt.datetime | None
    stare: StareJob


def _moment_iso(valoare: str | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(valoare) if valoare else None


def _moment_ms(ms: int | None) -> dt.datetime | None:
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC) if ms else None


def cron_complet(cron: str) -> str:
    """5 câmpuri (minut oră zi lună zi-săpt.) → 6, cu secunda 0: „la minut”. 6 câmpuri rămân neschimbate."""
    campuri = cron.split()
    if len(campuri) == 5:
        return "0 " + " ".join(campuri)
    if len(campuri) == 6:
        return " ".join(campuri)
    raise ProgramareInvalida(f"cron cu {len(campuri)} câmpuri; trebuie 5 (minut oră zi lună zi-săpt.) sau 6")


def programeaza_recurent(
    nume: str,
    cron: str,
    fluxul: Callable[..., Any],
    *,
    context: dict[str, Any] | None = None,
    fus_orar: str = FUS_IMPLICIT,
    coada: Coada | str = Coada.IO,
    recupereaza_ratate: bool = False,
) -> Programare:
    """Declară un job recurent. Nu scrie nimic în bază: scrierea o face `aplica_programari` la pornirea
    workerului (sau o poți apela explicit). `fluxul` primește `(moment, context)`; `moment` este tic-ul
    programat.

    `recupereaza_ratate`: la pornire, rulările ratate de la ultima declanșare se pun în coadă (fiecare
    tic o singură
    dată). Fără el, un worker repornit prinde doar ticurile din ultimele 30 de secunde.
    """
    if not NUME_PROGRAMARE.match(nume):
        raise ProgramareInvalida(f"nume de programare nepermis: {nume!r}")
    try:
        ZoneInfo(fus_orar)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ProgramareInvalida(f"fus orar necunoscut: {fus_orar!r}") from exc
    nume_coada = coada.value if isinstance(coada, Coada) else coada
    if not NUME_COADA.match(nume_coada):
        raise ProgramareInvalida(f"nume de coadă nepermis: {nume_coada!r}")
    try:
        argumente.verifica_valoare(context, "context")
    except ValueError as exc:
        raise ProgramareInvalida(str(exc)) from exc
    p = Programare(
        nume=nume,
        cron=cron_complet(cron),
        flux=nume_flux(fluxul),
        context=context,
        fus_orar=fus_orar,
        coada=nume_coada,
        recupereaza_ratate=recupereaza_ratate,
    )
    _registru[nume] = p
    return p


def programari_declarate() -> list[Programare]:
    return list(_registru.values())


def uita_declaratiile() -> None:
    """Golește registrul din memorie (nu atinge baza). Pentru teste: declarațiile sunt globale procesului."""
    _registru.clear()


def _intrare(p: Programare) -> ClientScheduleInput:
    return {
        "schedule_name": p.nume,
        "workflow_name": p.flux,
        "schedule": p.cron,
        "context": p.context,
        "automatic_backfill": p.recupereaza_ratate,
        "cron_timezone": p.fus_orar,
        "queue_name": p.coada,
    }


def aplica_programari(programari: list[Programare] | None = None) -> int:
    """Scrie în bază programările declarate (create sau înlocuite, atomic). Păstrează pauza și
    ultima declanșare. Întoarce câte s-au aplicat. Un cron invalid aruncă `ProgramareInvalida`."""
    de_aplicat = programari if programari is not None else programari_declarate()
    if not de_aplicat:
        return 0
    try:
        client().apply_schedules([_intrare(p) for p in de_aplicat])
    except Exception as exc:
        if "Invalid cron" in str(exc) or "Invalid timezone" in str(exc):
            raise ProgramareInvalida(str(exc)) from exc
        raise
    return len(de_aplicat)


def lista_programari() -> list[InfoProgramare]:
    return [
        InfoProgramare(
            nume=s["schedule_name"],
            cron=s["schedule"],
            flux=s["workflow_name"],
            stare="activa" if s["status"] == "ACTIVE" else "pe_pauza",
            fus_orar=s.get("cron_timezone"),
            coada=s.get("queue_name"),
            ultima_declansare=_moment_iso(s.get("last_fired_at")),
        )
        for s in client().list_schedules()
    ]


def pune_pe_pauza(nume: str) -> None:
    client().pause_schedule(nume)


def reia_programarea(nume: str) -> None:
    client().resume_schedule(nume)


def sterge_programarea(nume: str) -> None:
    _registru.pop(nume, None)
    client().delete_schedule(nume)


def declanseaza_acum(nume: str) -> str:
    """O rulare imediată a programării (în afara orarului). Întoarce identificatorul jobului."""
    return client().trigger_schedule(nume).get_workflow_id()


def recupereaza_ratate(nume: str, de_la: dt.datetime, pana_la: dt.datetime) -> list[str]:
    """Pune în coadă ticurile programării dintre cele două momente (capete excluse). Fiecare tic are un
    identificator determinist: cele deja puse în coadă sau rulate nu se dublează."""
    if de_la.tzinfo is None or pana_la.tzinfo is None:
        raise ProgramareInvalida("intervalul trebuie să aibă fus orar")
    return [h.get_workflow_id() for h in client().backfill_schedule(nume, de_la, pana_la)]


# --- sloturi ------------------------------------------------------------------------------------------


def programeaza_slot(
    la: dt.datetime,
    fluxul: Callable[..., Any],
    *args: Any,
    cheie: str,
    coada: Coada | str = Coada.IO,
    prioritate: Prioritate = Prioritate.P1,
    termen: dt.datetime | None = None,
    kwargs: dict[str, Any] | None = None,
) -> str:
    """Un job care pornește la momentul `la` (cu fus orar), nu înainte. `cheie` este obligatorie: identifică
    slotul (a doua programare cu aceeași cheie întoarce același job). Întoarce identificatorul jobului."""
    return trimite(
        fluxul, *args, coada=coada, prioritate=prioritate, termen=termen, cheie=cheie, la=la, kwargs=kwargs
    )


def anuleaza_slot(cheie: str) -> bool:
    """Anulează un slot care nu a pornit încă. Întoarce adevărat dacă l-a anulat."""
    w = client().list_workflows(workflow_ids=[cheie], load_input=False, load_output=False)
    if not w or stare_din_biblioteca(w[0].status) not in (StareJob.AMANAT, StareJob.IN_COADA):
        return False
    client().cancel_workflow(cheie)
    return True


def sloturi_viitoare(limita: int = 200) -> list[Slot]:
    """Sloturile care așteaptă (stare `amanat`), cele mai apropiate primele."""
    randuri = client().list_workflows(
        status=stare_biblioteca(StareJob.AMANAT), load_input=False, load_output=False, limit=limita
    )
    sloturi = [
        Slot(
            cheie=w.workflow_id,
            flux=w.name,
            coada=w.queue_name,
            la=_moment_ms(w.delay_until_epoch_ms),
            stare=stare_din_biblioteca(w.status),
        )
        for w in randuri
    ]
    return sorted(sloturi, key=lambda s: s.la or dt.datetime.max.replace(tzinfo=dt.UTC))
