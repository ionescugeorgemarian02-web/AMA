"""Fluxuri de probă pentru watchdog și coada de erori (F2.7), rulate în procesul testului."""

import threading
from collections import defaultdict

from app.operare import motor

_lock = threading.Lock()
INCERCARI: dict[str, int] = defaultdict(int)  # cheie -> de câte ori a rulat pasul
BLOCHEAZA_PRIMELE: dict[str, int] = {}  # job -> câte rulări ale pasului stau blocate
ESUEAZA_PRIMELE: dict[str, int] = {}  # job -> câte rulări ale pasului aruncă eroare
_eliberare = threading.Event()


def reseteaza() -> None:
    _eliberare.set()  # eliberează firele rămase blocate din testul anterior
    with _lock:
        INCERCARI.clear()
        BLOCHEAZA_PRIMELE.clear()
        ESUEAZA_PRIMELE.clear()
    _eliberare.clear()


def elibereaza() -> None:
    _eliberare.set()


def incercari(job: str) -> int:
    with _lock:
        return INCERCARI[job]


@motor.pas("watchdog.pas_bun")
def pas_bun(job: str) -> str:
    return "ok"


@motor.pas("watchdog.pas_stricat")
def pas_stricat(job: str) -> str:
    with _lock:
        INCERCARI[job] += 1
    raise motor.EroareDefinitiva(f"nu merge jobul {job} (cod 42)")


@motor.pas("watchdog.pas_alt_stricat")
def pas_alt_stricat(job: str) -> str:
    raise motor.EroareDefinitiva("altă problemă")


@motor.pas("watchdog.pas_autentificare")
def pas_autentificare(job: str) -> str:
    raise motor.EroareAutentificare("conectorul a pierdut autorizarea")


@motor.flux("watchdog.esueaza")
def esueaza(tenant_id: str, job: str) -> str:
    pas_bun(job)
    return pas_stricat(job)


@motor.flux("watchdog.esueaza_alt")
def esueaza_alt(tenant_id: str, job: str) -> str:
    return pas_alt_stricat(job)


@motor.flux("watchdog.autentificare")
def autentificare(tenant_id: str, job: str) -> str:
    return pas_autentificare(job)


@motor.pas("watchdog.pas_capricios")
def pas_capricios(job: str) -> str:
    """Eșuează (definitiv) primele `ESUEAZA_PRIMELE[job]` rulări, apoi reușește; sau stă blocat primele
    `BLOCHEAZA_PRIMELE[job]` rulări (până la `elibereaza`)."""
    with _lock:
        INCERCARI[job] += 1
        n = INCERCARI[job]
        de_blocat = BLOCHEAZA_PRIMELE.get(job, 0)
        de_esuat = ESUEAZA_PRIMELE.get(job, 0)
    if n <= de_blocat:
        _eliberare.wait(60)
    elif n <= de_esuat:
        raise motor.EroareDefinitiva(f"mai încearcă ({n})")
    return f"gata-{n}"


@motor.flux("watchdog.capricios", timp_maxim_sec=0.8)
def capricios(tenant_id: str, job: str) -> str:
    pas_bun(job)
    return pas_capricios(job)
