"""Pornirea și oprirea executorului. Se apelează doar din procesul `worker` (și din teste care îl cer)."""

import threading

from dbos import DBOS, DBOSConfig

from app.config import Settings, get_settings
from app.logging import get_logger
from app.operare.motor import executie

log = get_logger("app.motor")
_lock = threading.RLock()


def configurare(s: Settings) -> DBOSConfig:
    """Configurarea bibliotecii, din `Settings`. Aplicația rulează ca `ama_app`: fără drept de DDL, deci
    `run_migrations=False` (schema o creează `migrare.migreaza_sistem`, ca proprietar, la livrare)."""
    return {
        "name": executie.NUME_APLICATIE,
        "system_database_url": s.database_url,
        "dbos_system_schema": s.motor_schema,
        "application_version": s.motor_versiune,
        "executor_id": s.worker_id,
        "run_migrations": False,
        "sys_db_pool_size": s.motor_pool,
        "log_level": s.log_level.upper(),
        "enable_otlp": False,
    }


def pornit() -> bool:
    return executie.pornit()


def porneste() -> None:
    """Pornește executorul: se conectează, verifică schema, reia joburile rămase în lucru ale acestui worker
    (același `AMA_WORKER_ID`) și începe să le ia din cozi. Idempotent."""
    with _lock:
        if executie.pornit():
            return
        s = get_settings()
        try:
            executie.preinregistreaza_cozi()
        except Exception as exc:  # schema lipsește etc.: lansarea de mai jos dă eroarea clară
            log.warning(
                "cozile nu au putut fi scrise înainte de lansare", extra={"tip_eroare": type(exc).__name__}
            )
        DBOS(config=configurare(s))
        try:
            DBOS.launch()
            executie.inregistreaza_cozi()
        except BaseException:
            DBOS.destroy()
            raise
        executie.seteaza_pornit(True)
        log.info("motor pornit", extra={"worker": s.worker_id, "versiune_joburi": s.motor_versiune})


def opreste(asteptare_sec: int | None = None) -> None:
    """Oprire curată: nu mai ia joburi noi, așteaptă cele în curs cel mult `asteptare_sec` (implicit
    `AMA_WORKER_OPRIRE_SEC`); ce nu se termină rămâne în lucru în bază și se reia la repornire."""
    with _lock:
        if not executie.pornit():
            return
        s = get_settings()
        DBOS.destroy(
            workflow_completion_timeout_sec=s.worker_oprire_sec if asteptare_sec is None else asteptare_sec
        )
        executie.seteaza_pornit(False)
        log.info("motor oprit", extra={"worker": s.worker_id})
