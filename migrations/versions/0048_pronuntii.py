"""Dicționarul de pronunție al clientului (F8.2, docs/14 §14.4)

Revizia: 0048
Anterioara: 0047

- `pronuntii`: termen (nume de brand, cuvânt străin) -> cum se citește, pe client; un termen o singură dată.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE pronuntii (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            termen text NOT NULL CHECK (length(btrim(termen)) BETWEEN 1 AND 80),
            pronuntie text NOT NULL CHECK (length(btrim(pronuntie)) BETWEEN 1 AND 160 AND pronuntie !~ '[0-9]'),
            creat_de uuid REFERENCES utilizatori (id),
            creat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE UNIQUE INDEX pronuntii_termen ON pronuntii (tenant_id, lower(termen))")
    activeaza_rls_tenant(op.execute, "pronuntii")


def downgrade() -> None:
    op.execute("DROP TABLE pronuntii")
