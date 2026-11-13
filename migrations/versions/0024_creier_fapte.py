"""Creierul: extragerea faptelor din materiale (F4.6, docs/09 §9.3)

Revizia: 0024
Anterioara: 0023

- `creier_extrageri`: un rând pentru fiecare pasaj extras cu o versiune de prompt (idempotență: reluarea fluxului nu cheamă
  din nou modelul pentru pasajele terminate), cu câte fapte s-au propus, câte erau duplicate și propunerile respinse de
  verificatorul de citate (motiv, afirmație, citat). `pasaj_id` nu are cheie străină: pasajele se înlocuiesc la reindexare.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE creier_extrageri (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            pasaj_id uuid NOT NULL,
            document_id uuid NOT NULL,
            prompt text NOT NULL CHECK (length(prompt) BETWEEN 3 AND 100),
            propuse integer NOT NULL DEFAULT 0 CHECK (propuse >= 0),
            duplicate integer NOT NULL DEFAULT 0 CHECK (duplicate >= 0),
            respinse jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(respinse) = 'array'),
            model text,
            creat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (pasaj_id, prompt)
        )"""
    )
    op.execute("CREATE INDEX creier_extrageri_client ON creier_extrageri (tenant_id, document_id)")
    activeaza_rls_tenant(op.execute, "creier_extrageri", drepturi="SELECT, INSERT")


def downgrade() -> None:
    op.execute("DROP TABLE creier_extrageri")
