"""Programări (F12.5, docs/17 §17.6)

Revizia: 0098
Anterioara: 0097

- `crm_programari`: apelurile rezervate de lead-uri, pe sloturi fixe ale unui singur calendar; un slot are cel
  mult o programare confirmată (index unic parțial). Jetonul de anulare e păstrat doar ca hash. Reamintirile
  trimise (cu o zi și cu o oră înainte) se notează, ca să nu plece de două ori.
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0098"
down_revision = "0097"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE crm_programari (
            id uuid PRIMARY KEY,
            lead_id uuid NOT NULL REFERENCES crm_leaduri (id),
            contact_id uuid NOT NULL REFERENCES crm_contacte (id),
            tip text NOT NULL CHECK (tip IN ('apel_descoperire')),
            inceput timestamptz NOT NULL,
            sfarsit timestamptz NOT NULL CHECK (sfarsit > inceput),
            stare text NOT NULL DEFAULT 'confirmata' CHECK (stare IN ('confirmata', 'anulata')),
            jeton_hash text NOT NULL UNIQUE,
            reamintit_24h boolean NOT NULL DEFAULT false,
            reamintit_1h boolean NOT NULL DEFAULT false,
            creat_la timestamptz NOT NULL DEFAULT now(),
            anulat_la timestamptz
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX crm_programari_slot ON crm_programari (inceput) WHERE stare = 'confirmata'"
    )
    activeaza_rls(op.execute, "crm_programari")
    op.execute(
        f"CREATE POLICY crm_programari_agentie ON crm_programari USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON crm_programari TO ama_app")


def downgrade() -> None:
    op.execute("DROP TABLE crm_programari")
