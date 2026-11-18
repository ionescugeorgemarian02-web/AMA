"""FS.5 Starea sincronizării Shopify."""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0123"
down_revision = "0122"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE comert_sincronizari (
        tenant_id uuid NOT NULL REFERENCES clienti(id), magazin text NOT NULL,
        stare text NOT NULL CHECK(stare IN ('in_curs','succes','eroare')),
        ultima_reusita timestamptz, PRIMARY KEY(tenant_id,magazin)
    )""")
    activeaza_rls_tenant(op.execute, "comert_sincronizari")


def downgrade() -> None:
    op.execute("DROP TABLE comert_sincronizari")
