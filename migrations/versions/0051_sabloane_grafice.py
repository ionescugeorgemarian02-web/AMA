"""Șabloanele grafice ale brandului (F8.10, docs/14 §14.10)

Revizia: 0051
Anterioara: 0050

- `sabloane_grafice`: un șablon pe tip și versiune (citat, ofertă, sfat, rezultat, anunț, copertă video), ca date
  (zone de text, logo, fotografie) cu identitatea vizuală din care a fost făcut.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE sabloane_grafice (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            tip text NOT NULL CHECK (tip IN ('citat', 'oferta', 'sfat', 'rezultat', 'anunt', 'coperta_video')),
            versiune int NOT NULL DEFAULT 1 CHECK (versiune >= 1),
            definitie jsonb NOT NULL CHECK (jsonb_typeof(definitie) = 'object'),
            creat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, tip, versiune)
        )"""
    )
    activeaza_rls_tenant(op.execute, "sabloane_grafice")


def downgrade() -> None:
    op.execute("DROP TABLE sabloane_grafice")
