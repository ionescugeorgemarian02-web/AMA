"""Schema bibliotecii („tabelele de sistem”) în aceeași bază, schema `dbos` (ADR-02: un singur Postgres).

Se creează și se actualizează de proprietar (`ama_owner`), ca pas explicit la livrare, după `alembic
upgrade head`:

    python -m app.operare.motor.migrare

La rulare, `ama_app` primește doar `SELECT, INSERT, UPDATE, DELETE` pe tabele, folosire a secvențelor
și execuția
funcțiilor; nu primește `CREATE`, `TRUNCATE`, `REFERENCES`, `TRIGGER`. Execuția este idempotentă: se
poate rula la
fiecare livrare (biblioteca aplică doar migrările care lipsesc, apoi drepturile se refac).
"""

import sys

from dbos import DBOS
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.db import bootstrap
from app.logging import configure_logging, get_logger

log = get_logger("app.motor.migrare")
ROL_APLICATIE = "ama_app"


def migreaza_sistem(url_proprietar: str | None = None, *, schema: str | None = None) -> None:
    """Creează/actualizează schema bibliotecii ca proprietar, apoi restrânge drepturile lui `ama_app`."""
    s = get_settings()
    url = url_proprietar or s.database_owner_url
    sch = schema or s.motor_schema
    DBOS.migrate(url, schema=sch, application_role=ROL_APLICATIE)
    dsn = make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    bootstrap.restrange_drepturi_schema(dsn, sch, ROL_APLICATIE)
    log.info("schema motorului pregătită", extra={"schema": sch})


def main() -> int:
    configure_logging(get_settings().log_level)
    migreaza_sistem()
    return 0


if __name__ == "__main__":
    sys.exit(main())
