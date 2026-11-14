"""Pașapoartele fișierelor finale (F8.11, docs/14 §14.3, docs/21 §21.9, ADR-08)

Revizia: 0052
Anterioara: 0051

- `pasapoarte`: un pașaport pe activ final (amprenta, componentele cu licențele lor, generarea, verdictele G5/G6,
  eticheta pe fiecare canal).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE pasapoarte (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            activ_id uuid NOT NULL UNIQUE REFERENCES active (id),
            continut jsonb NOT NULL CHECK (jsonb_typeof(continut) = 'object' AND continut ? 'etichete'),
            creat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    activeaza_rls_tenant(op.execute, "pasapoarte")


def downgrade() -> None:
    op.execute("DROP TABLE pasapoarte")
