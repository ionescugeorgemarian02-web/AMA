"""Exportul și ștergerea datelor clientului: cererile de ștergere (F7.7, docs/19 §19.2 „Date”, docs/21)

Revizia: 0044
Anterioara: 0043

- `cereri_stergere`: cererea titularului (cine, când), executarea ei (când, câte rânduri pe tabel). Rândul se
  păstrează după ștergere, ca dovadă, împreună cu jurnalul de audit; nu conține date de business.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE cereri_stergere (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            cerut_de uuid,
            stare text NOT NULL DEFAULT 'cerut' CHECK (stare IN ('cerut', 'executat', 'esuat')),
            rezultat jsonb NOT NULL DEFAULT '{}'::jsonb,
            creat_la timestamptz NOT NULL DEFAULT now(),
            executat_la timestamptz,
            CHECK (stare <> 'executat' OR executat_la IS NOT NULL)
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX cereri_stergere_una_deschisa ON cereri_stergere (tenant_id) WHERE stare = 'cerut'"
    )
    activeaza_rls_tenant(op.execute, "cereri_stergere")


def downgrade() -> None:
    op.execute("DROP TABLE cereri_stergere")
