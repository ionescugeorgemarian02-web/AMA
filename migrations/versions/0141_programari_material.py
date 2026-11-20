"""Numărul zilnic de programări confirmate în exportul clientului, pe material."""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0141"
down_revision = "0140"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE programari_material (
        tenant_id uuid NOT NULL REFERENCES clienti(id), livrabil_id uuid NOT NULL REFERENCES livrabile(id),
        zi date NOT NULL, numar integer NOT NULL CHECK(numar >= 0),
        PRIMARY KEY(tenant_id, livrabil_id, zi))""")
    activeaza_rls_tenant(op.execute, "programari_material")


def downgrade() -> None:
    op.execute("DROP TABLE programari_material")
