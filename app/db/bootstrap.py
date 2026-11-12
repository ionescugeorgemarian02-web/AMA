"""Pregătirea clusterului (o dată, ca superutilizator): rolurile și extensiile.

Migrările rulează apoi ca `ama_owner`.

Folosit de fixture-ul de test și de pregătirea VPS-ului. Nu rulează niciodată în aplicație.
"""

import psycopg
from psycopg import sql

ROL_OWNER = "ama_owner"
ROL_APP = "ama_app"
EXTENSII_SUPERUSER = ("vector",)  # nu sunt „trusted”: le creează superutilizatorul, dacă sunt disponibile


def _rol(cur: psycopg.Cursor[tuple[object, ...]], nume: str, parola: str | None, extra: str) -> None:
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (nume,))
    verb = "ALTER" if cur.fetchone() else "CREATE"
    stmt = sql.SQL(f"{verb} ROLE {{}} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE {extra}").format(
        sql.Identifier(nume)
    )
    if parola is not None:
        stmt = stmt + sql.SQL(" PASSWORD {}").format(sql.Literal(parola))
    cur.execute(stmt)


def pregateste_roluri(
    admin_dsn: str, *, parola_owner: str | None = None, parola_app: str | None = None
) -> None:
    """Creează (idempotent) cele două roluri: proprietarul tabelelor și rolul de execuție al aplicației."""
    with psycopg.connect(admin_dsn, autocommit=True) as conn, conn.cursor() as cur:
        _rol(cur, ROL_OWNER, parola_owner, "NOINHERIT")
        _rol(cur, ROL_APP, parola_app, "NOINHERIT")


def pregateste_baza(admin_dsn_baza: str, nume_baza: str) -> None:
    """Conectat ca superutilizator la baza țintă: drepturi de conectare și extensiile ne-„trusted”."""
    with psycopg.connect(admin_dsn_baza, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(nume_baza)))
        cur.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(nume_baza), sql.Identifier(ROL_APP)
            )
        )
        for ext in EXTENSII_SUPERUSER:
            cur.execute("SELECT 1 FROM pg_available_extensions WHERE name = %s", (ext,))
            if cur.fetchone():
                cur.execute(sql.SQL("CREATE EXTENSION IF NOT EXISTS {}").format(sql.Identifier(ext)))


# Drepturi date implicit de biblioteca de workflow-uri rolului aplicației; aplicația nu le folosește.
DREPTURI_RETRASE_MOTOR = ("TRUNCATE", "REFERENCES", "TRIGGER")


def restrange_drepturi_schema(owner_dsn: str, schema: str, rol: str = ROL_APP) -> None:
    """Conectat ca proprietar: retrage de la `rol` drepturile de structură pe tabelele schemei (existente și
    viitoare). Idempotent. Apelat de `app.operare.motor.migrare` după ce biblioteca și-a creat schema."""
    drepturi = sql.SQL(", ").join(sql.SQL(d) for d in DREPTURI_RETRASE_MOTOR)
    with psycopg.connect(owner_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL("REVOKE {} ON ALL TABLES IN SCHEMA {} FROM {}").format(
                drepturi, sql.Identifier(schema), sql.Identifier(rol)
            )
        )
        cur.execute(
            sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} REVOKE {} ON TABLES FROM {}").format(
                sql.Identifier(schema), drepturi, sql.Identifier(rol)
            )
        )
