"""Formularul de audit: leaduri cu opt-in dublu, auditurile și efectele de sistem (F7.2, docs/19 §19.1, docs/17)

Revizia: 0040
Anterioara: 0039

- `efecte_sistem`: „outbox”-ul efectelor externe fără livrabil (email, plăți), cu cheie de idempotență unică;
  aceeași disciplină ca `efecte_de_trimis` (F2.5). `tenant_id` lipsește pentru efectele agenției (emailul către un lead).
- `leaduri`: firmele care au cerut auditul; jetonul de confirmare se ține doar ca SHA-256. Opt-in dublu: lead-ul
  devine `confirmat` doar din linkul primit pe email. Date ale agenției (până la conversia în client).
- `audituri`: raportul produs de motorul de audit (BigBrain, prin adaptor) pentru un lead confirmat.
"""

from alembic import op

from app.db.rls import activeaza_rls, activeaza_rls_tenant

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"


def politici_agentie(tabel: str) -> None:
    activeaza_rls(op.execute, tabel)
    op.execute(f"CREATE POLICY {tabel}_agentie ON {tabel} USING ({AGENTIE}) WITH CHECK ({AGENTIE})")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {tabel} TO ama_app")


def upgrade() -> None:
    op.execute(
        """CREATE TABLE efecte_sistem (
            id uuid PRIMARY KEY,
            tenant_id uuid REFERENCES clienti (id),
            tip text NOT NULL CHECK (tip IN ('email', 'plata')),
            cheia text NOT NULL UNIQUE CHECK (length(cheia) <= 300),
            stare text NOT NULL DEFAULT 'in_asteptare'
                CHECK (stare IN ('in_asteptare', 'trimis', 'esuat', 'anulat')),
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            incercari integer NOT NULL DEFAULT 0 CHECK (incercari >= 0),
            id_extern text,
            link text,
            eroare text,
            creat_la timestamptz NOT NULL DEFAULT now(),
            trimis_la timestamptz
        )"""
    )
    op.execute("CREATE INDEX efecte_sistem_deschise ON efecte_sistem (creat_la) WHERE stare = 'in_asteptare'")
    activeaza_rls_tenant(op.execute, "efecte_sistem")
    op.execute(
        """CREATE TABLE leaduri (
            id uuid PRIMARY KEY,
            email text NOT NULL CHECK (length(email) BETWEEN 6 AND 254),
            firma text NOT NULL CHECK (length(firma) BETWEEN 2 AND 200),
            site_url text NOT NULL CHECK (site_url ~ '^https?://' AND length(site_url) <= 300),
            sursa text NOT NULL DEFAULT 'audit',
            stare text NOT NULL DEFAULT 'neconfirmat'
                CHECK (stare IN ('neconfirmat', 'confirmat', 'audit_gata', 'client', 'retras')),
            jeton_hash text NOT NULL UNIQUE,
            consimtamant_la timestamptz NOT NULL,
            confirmat_la timestamptz,
            tenant_id uuid REFERENCES clienti (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            CHECK (stare = 'neconfirmat' OR stare = 'retras' OR confirmat_la IS NOT NULL)
        )"""
    )
    op.execute("CREATE INDEX leaduri_email ON leaduri (lower(email))")
    politici_agentie("leaduri")
    op.execute(
        """CREATE TABLE audituri (
            id uuid PRIMARY KEY,
            lead_id uuid NOT NULL REFERENCES leaduri (id),
            stare text NOT NULL DEFAULT 'in_curs' CHECK (stare IN ('in_curs', 'gata', 'esuat')),
            motor text NOT NULL,
            raport jsonb,
            eroare text,
            creat_la timestamptz NOT NULL DEFAULT now(),
            gata_la timestamptz,
            CHECK (stare <> 'gata' OR (raport IS NOT NULL AND gata_la IS NOT NULL))
        )"""
    )
    op.execute("CREATE UNIQUE INDEX audituri_unul_pe_lead ON audituri (lead_id)")
    politici_agentie("audituri")


def downgrade() -> None:
    op.execute("DROP TABLE audituri")
    op.execute("DROP TABLE leaduri")
    op.execute("DROP TABLE efecte_sistem")
