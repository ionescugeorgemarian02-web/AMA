"""Generatorul video extern (F16.5, docs/14 §14.2)

Revizia: 0107
Anterioara: 0106

- `video_generari`: fiecare cerere către generatorul extern: promptul, durata (inserturi de 3–6 s), costul
  rezervat înainte de apel, starea (`rezervat` -> `gata` / `esuat`; `refuzat` = peste plafon, fără apel) și
  activul rezultat. Costul `rezervat` + `gata` din luna curentă nu depășește plafonul lunar al clientului.
Date ale clientului: RLS pe `tenant_id`.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0107"
down_revision = "0106"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE video_generari (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            prompt text NOT NULL CHECK (length(prompt) BETWEEN 3 AND 1000),
            durata_sec numeric(4, 1) NOT NULL CHECK (durata_sec BETWEEN 3 AND 6),
            furnizor text NOT NULL CHECK (length(furnizor) BETWEEN 1 AND 60),
            cost_bani bigint NOT NULL CHECK (cost_bani >= 0),
            stare text NOT NULL CHECK (stare IN ('rezervat', 'gata', 'esuat', 'refuzat')),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 500),
            activ_id uuid REFERENCES active (id),
            la timestamptz NOT NULL DEFAULT now(),
            CHECK (stare <> 'gata' OR activ_id IS NOT NULL)
        )"""
    )
    op.execute("CREATE INDEX video_generari_luna ON video_generari (tenant_id, la)")
    activeaza_rls_tenant(op.execute, "video_generari")


def downgrade() -> None:
    op.execute("DROP TABLE video_generari")
