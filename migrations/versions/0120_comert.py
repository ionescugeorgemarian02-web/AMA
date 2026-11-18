"""FS.1: magazin și autorizare Shopify."""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0120"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE comert_magazine (
        id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES clienti(id),
        magazin text NOT NULL, token_criptat bytea,
        stare_hash bytea, expira_la timestamptz,
        coduri_reducere jsonb NOT NULL DEFAULT '{}', UNIQUE(tenant_id,magazin)
    )""")
    activeaza_rls_tenant(op.execute, "comert_magazine")


def downgrade() -> None:
    op.execute("DROP TABLE comert_magazine")
