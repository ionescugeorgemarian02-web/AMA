"""Lista de conturi-țintă (F12.9, docs/17 §17.2)

Revizia: 0102
Anterioara: 0101

- `crm_conturi_tinta`: firme (nu persoane) dintr-o nișă și o localitate, din surse publice, cu mini-audit și
  trei argumente de discuție. Tabelul nu are coloane pentru persoane (nume de om, email, telefon); aplicația
  filtrează datele personale înainte de scriere. Platforma nu trimite singură mesaje către această listă.
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE crm_conturi_tinta (
            id uuid PRIMARY KEY,
            lista text NOT NULL CHECK (lista ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND length(lista) <= 80),
            nume text NOT NULL CHECK (length(nume) BETWEEN 2 AND 200),
            domeniu text NOT NULL CHECK (length(domeniu) BETWEEN 3 AND 253),
            nisa text NOT NULL CHECK (length(nisa) BETWEEN 2 AND 60),
            localitate text NOT NULL CHECK (length(localitate) BETWEEN 2 AND 80),
            site text NOT NULL CHECK (length(site) <= 300),
            pagini jsonb NOT NULL DEFAULT '[]',
            semnale jsonb NOT NULL DEFAULT '[]',
            mini_audit jsonb NOT NULL,
            argumente jsonb NOT NULL CHECK (jsonb_array_length(argumente) = 3),
            sursa text NOT NULL CHECK (sursa IN ('registru_public', 'harti_deschise', 'site_firma')),
            stare text NOT NULL DEFAULT 'nou' CHECK (stare IN ('nou', 'contactat', 'respins')),
            creat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (lista, domeniu)
        )"""
    )
    activeaza_rls(op.execute, "crm_conturi_tinta")
    op.execute(
        f"CREATE POLICY crm_conturi_tinta_agentie ON crm_conturi_tinta USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON crm_conturi_tinta TO ama_app")


def downgrade() -> None:
    op.execute("DROP TABLE crm_conturi_tinta")
