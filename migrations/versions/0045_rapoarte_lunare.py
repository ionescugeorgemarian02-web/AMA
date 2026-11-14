"""Raportul lunar, prima formă (F7.8, docs/19 §19.6)

Revizia: 0045
Anterioara: 0044

- `rapoarte_lunare`: conținutul raportului pe client și lună (livrabile față de pachet, aprobări, planul lunii
  următoare, ce avem nevoie de la client); fără metrici de performanță până la F10. Unul pe client și lună.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE rapoarte_lunare (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            luna date NOT NULL CHECK (extract(day FROM luna) = 1),
            continut jsonb NOT NULL,
            stare text NOT NULL DEFAULT 'generat' CHECK (stare IN ('generat', 'trimis')),
            generat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, luna)
        )"""
    )
    activeaza_rls_tenant(op.execute, "rapoarte_lunare")


def downgrade() -> None:
    op.execute("DROP TABLE rapoarte_lunare")
