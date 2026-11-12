"""Baza: extensii și funcțiile de context pentru RLS

Revizia: 0001
Anterioara: -
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UUID_RE = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
EXTENSII = ("pg_trgm", "citext", "vector")


def upgrade() -> None:
    # pg_trgm și citext sunt „trusted”; `vector` îl creează pregătirea bazei (superutilizator), dacă există.
    for ext in EXTENSII:
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = '{ext}') THEN "
            f"CREATE EXTENSION IF NOT EXISTS {ext}; END IF; END $$"
        )
    op.execute("GRANT USAGE ON SCHEMA public TO ama_app")

    # Funcțiile citesc setările tranzacției. Întorc NULL/false la valori lipsă sau invalide: refuz implicit.
    for nume in ("tenant_id", "user_id"):
        op.execute(
            f"""CREATE FUNCTION ama_{nume}() RETURNS uuid LANGUAGE sql STABLE PARALLEL SAFE AS $$
                SELECT CASE WHEN s ~ '{UUID_RE}' THEN s::uuid END
                FROM (SELECT current_setting('app.{nume}', true) AS s) t
            $$"""
        )
    for fct, setare in (("ama_agency", "app.agency"), ("ama_auth", "app.auth")):
        op.execute(
            f"""CREATE FUNCTION {fct}() RETURNS boolean LANGUAGE sql STABLE PARALLEL SAFE AS $$
                SELECT COALESCE(current_setting('{setare}', true), '') = '1'
            $$"""
        )


def downgrade() -> None:
    for fct in ("ama_auth", "ama_agency", "ama_user_id", "ama_tenant_id"):
        op.execute(f"DROP FUNCTION {fct}()")
    # Se șterg doar extensiile create de rolul curent; cele create de superutilizator rămân.
    for ext in EXTENSII:
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = '{ext}' "
            f"AND extowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)) THEN "
            f"DROP EXTENSION {ext}; END IF; END $$"
        )
