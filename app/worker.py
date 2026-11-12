"""Procesul `worker`: rulează fluxurile durabile (F2.1). Pornire: `python -m app.worker`.

Topologia (ADR-03, 6.4): procesul web doar pune joburi în coadă; execuția are loc aici. Workerul se oprește
curat la SIGTERM/SIGINT (așteaptă joburile în curs cel mult `AMA_WORKER_OPRIRE_SEC`, restul rămâne în bază).
La repornire, cu același `AMA_WORKER_ID`, își reia joburile rămase în lucru, de la ultimul pas salvat.
Repornirea automată după o cădere o face politica `restart` a serviciului din compose.

Tot aici trăiește watchdog-ul (F2.7): bătăi de inimă, joburi blocate, coada de erori.
`python -m app.worker --verifica` este verificarea de sănătate a serviciului: iese cu 0 dacă workerul a
dat semn de viață recent.
"""

import importlib
import logging
import os
import signal
import sys
import threading
from types import FrameType

from app.config import get_settings
from app.logging import configure_logging, get_logger

log = get_logger("app.worker")

# Modulele care declară fluxuri (`@motor.flux`). Se adaugă aici pe măsură ce apar (F3 …): workerul
# trebuie să le fi importat înainte de pornire, altfel nu poate rula joburile lor.
MODULE_FLUXURI: tuple[str, ...] = ("app.productie.fluxuri", "app.operare.efecte", "app.gateway.fluxuri")


def _incarca_module() -> None:
    s = get_settings()
    module = list(MODULE_FLUXURI)
    if s.env == "test" and s.worker_module_test:
        module += [m.strip() for m in s.worker_module_test.split(",") if m.strip()]
    for m in module:
        importlib.import_module(m)


def verifica() -> int:
    """Verificarea de sănătate (compose): 0 dacă acest worker a bătut în ultimele `AMA_WORKER_TIMEOUT_SEC`."""
    from app.operare import semnale

    s = get_settings()
    try:
        viu = semnale.este_viu(s.worker_id, s.worker_timeout_sec)
    except Exception:
        return 1
    return 0 if viu else 1


def main() -> int:
    from app.operare import motor
    from app.operare.watchdog import Watchdog

    s = get_settings()
    configure_logging(s.log_level)
    s.require_secrets()
    oprire = threading.Event()

    def la_semnal(semnal: int, _cadru: FrameType | None) -> None:
        log.info("semnal de oprire", extra={"semnal": signal.Signals(semnal).name})
        oprire.set()

    signal.signal(signal.SIGTERM, la_semnal)
    signal.signal(signal.SIGINT, la_semnal)

    _incarca_module()
    motor.porneste()
    watchdog = Watchdog.din_configurare()
    watchdog.porneste()
    log.info("worker pornit", extra={"worker": s.worker_id, "pid": os.getpid()})
    try:
        oprire.wait()
    finally:
        motor.opreste()
        watchdog.opreste()  # după motor: cât așteaptă joburile în curs, workerul continuă să bată
    log.info("worker oprit curat", extra={"worker": s.worker_id})
    _iesire_fara_fire_blocate()
    return 0


def _iesire_fara_fire_blocate() -> None:
    """Un job care nu s-a încheiat în fereastra de oprire încă rulează într-un fir al bibliotecii, iar
    Python nu iese cât mai are fire care nu sunt „daemon”. Jobul rămâne în lucru în bază și se reia la
    repornire (pașii salvați nu se repetă), deci ieșirea imediată nu pierde nimic."""
    ramase = [t for t in threading.enumerate() if t is not threading.main_thread() and not t.daemon]
    if ramase:
        log.warning("ies cu joburi neterminate; se reiau la repornire", extra={"fire": len(ramase)})
        logging.shutdown()
        sys.stdout.flush()
        os._exit(0)


if __name__ == "__main__":
    sys.exit(verifica() if "--verifica" in sys.argv[1:] else main())
