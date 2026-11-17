"""Învățare: lecțiile folosite la un livrabil (F11.2, docs/11 §11.3: „generatorul notează ce lecții a folosit”)

Revizia: 0091
Anterioara: 0090

- `lectii_folosite`: ce lecții active au intrat în contextul autorului pentru un livrabil. `socotit` devine
  adevărat când decizia omului asupra livrabilului a actualizat contoarele lecției (o singură dată).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE lectii_folosite (
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            lectie_id uuid NOT NULL REFERENCES lectii (id),
            socotit boolean NOT NULL DEFAULT false,
            folosita_la timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (livrabil_id, lectie_id)
        )"""
    )
    activeaza_rls_tenant(op.execute, "lectii_folosite")


def downgrade() -> None:
    op.execute("DROP TABLE lectii_folosite")
