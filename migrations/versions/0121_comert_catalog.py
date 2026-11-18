"""FS.2 Catalog Shopify."""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0121"
down_revision = "0120"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE comert_produse (
        tenant_id uuid NOT NULL REFERENCES clienti(id), magazin text NOT NULL,
        id_extern text NOT NULL, titlu text NOT NULL, activ boolean NOT NULL,
        versiune timestamptz NOT NULL, PRIMARY KEY(tenant_id, magazin, id_extern)
    )""")
    activeaza_rls_tenant(op.execute, "comert_produse")


def downgrade() -> None:
    op.execute("DROP TABLE comert_produse")
