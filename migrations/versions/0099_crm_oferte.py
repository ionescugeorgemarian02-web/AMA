"""Generatorul de oferte (F12.6, docs/17 §17.7, J5)

Revizia: 0099
Anterioara: 0098

- `crm_oferte`: oferta scrisă din audit și din pachete, cu verificările ei; stă „de aprobat” până decide
  proprietarul. Un lead are cel mult o ofertă de aprobat odată (index unic parțial).
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE crm_oferte (
            id uuid PRIMARY KEY,
            lead_id uuid NOT NULL REFERENCES crm_leaduri (id),
            pachet text NOT NULL CHECK (pachet IN ('start', 'crestere', 'pro')),
            pret_lunar integer NOT NULL CHECK (pret_lunar > 0),
            setup integer NOT NULL CHECK (setup >= 0),
            continut jsonb NOT NULL,
            verificari jsonb NOT NULL DEFAULT '{}',
            stare text NOT NULL DEFAULT 'de_aprobat'
                CHECK (stare IN ('de_aprobat', 'aprobata', 'respinsa', 'blocata')),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 500),
            decis_de uuid REFERENCES utilizatori (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            decis_la timestamptz
        )"""
    )
    op.execute("CREATE UNIQUE INDEX crm_oferte_deschisa ON crm_oferte (lead_id) WHERE stare = 'de_aprobat'")
    activeaza_rls(op.execute, "crm_oferte")
    op.execute(f"CREATE POLICY crm_oferte_agentie ON crm_oferte USING ({AGENTIE}) WITH CHECK ({AGENTIE})")
    op.execute("GRANT SELECT, INSERT, UPDATE ON crm_oferte TO ama_app")


def downgrade() -> None:
    op.execute("DROP TABLE crm_oferte")
