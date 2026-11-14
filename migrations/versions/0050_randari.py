"""Randările video (F8.6, docs/14 §14.5–14.9, §14.11)

Revizia: 0050
Anterioara: 0049

- `randari`: lista de montaj (date, re-randabilă identic), starea, videoul rezultat (activ), măsurătorile
  randării (timp, memorie de vârf; F8.9) și calitatea (`ciorna` / `final`).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE randari (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid REFERENCES livrabile (id),
            lista jsonb NOT NULL CHECK (jsonb_typeof(lista) = 'object'),
            calitate text NOT NULL DEFAULT 'final' CHECK (calitate IN ('ciorna', 'final')),
            stare text NOT NULL DEFAULT 'in_lucru' CHECK (stare IN ('in_lucru', 'gata', 'esuat', 'respins')),
            activ_id uuid REFERENCES active (id),
            masuratori jsonb NOT NULL DEFAULT '{}'::jsonb,
            control jsonb NOT NULL DEFAULT '{}'::jsonb,
            creat_la timestamptz NOT NULL DEFAULT now(),
            terminat_la timestamptz,
            CHECK (stare <> 'gata' OR activ_id IS NOT NULL)
        )"""
    )
    activeaza_rls_tenant(op.execute, "randari")


def downgrade() -> None:
    op.execute("DROP TABLE randari")
