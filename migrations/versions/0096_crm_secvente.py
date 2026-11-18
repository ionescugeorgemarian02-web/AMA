"""Secvența de după audit (F12.3, docs/17 §17.3)

Revizia: 0096
Anterioara: 0083

- `crm_secvente`: înscrierea unui contact într-o secvență de emailuri (o singură dată pe secvență), pasul
  următor și momentul lui; o secvență oprită (dezabonare, acord retras, lead avansat) nu mai pornește.
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0096"
down_revision = "0083"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE crm_secvente (
            id uuid PRIMARY KEY,
            contact_id uuid NOT NULL REFERENCES crm_contacte (id),
            lead_id uuid REFERENCES crm_leaduri (id),
            secventa text NOT NULL CHECK (secventa IN ('dupa_audit')),
            pas integer NOT NULL DEFAULT 0 CHECK (pas >= 0),
            pornita_la timestamptz NOT NULL,
            urmatorul_la timestamptz,
            stare text NOT NULL DEFAULT 'activa' CHECK (stare IN ('activa', 'terminata', 'oprita')),
            motiv_oprire text NOT NULL DEFAULT '' CHECK (length(motiv_oprire) <= 80),
            UNIQUE (contact_id, secventa)
        )"""
    )
    op.execute("CREATE INDEX crm_secvente_scadente ON crm_secvente (urmatorul_la) WHERE stare = 'activa'")
    activeaza_rls(op.execute, "crm_secvente")
    op.execute(f"CREATE POLICY crm_secvente_agentie ON crm_secvente USING ({AGENTIE}) WITH CHECK ({AGENTIE})")
    op.execute("GRANT SELECT, INSERT, UPDATE ON crm_secvente TO ama_app")


def downgrade() -> None:
    op.execute("DROP TABLE crm_secvente")
