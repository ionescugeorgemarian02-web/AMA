"""FS.3 comenzi și clienți ai tenantului."""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0122"
down_revision = "0121"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE comert_date (
        tenant_id uuid NOT NULL REFERENCES clienti(id), magazin text NOT NULL,
        tip text NOT NULL CHECK(tip IN ('comanda','client')), id_extern text NOT NULL,
        date jsonb NOT NULL, creata_la timestamptz, email_criptat bytea, versiune timestamptz NOT NULL,
        PRIMARY KEY(tenant_id,magazin,tip,id_extern)
    )""")
    activeaza_rls_tenant(op.execute, "comert_date")


def downgrade() -> None:
    op.execute("DROP TABLE comert_date")
