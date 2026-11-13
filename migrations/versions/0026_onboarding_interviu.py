"""Onboarding: sesiunea de interviu și întrebările ei (F4.4, docs/19 §19.3)

Revizia: 0026
Anterioara: 0025

- `onboarding_sesiuni`: interviul unui client, reluabil de unde a rămas (cel mult o sesiune deschisă pe client),
  cu brieful în lucru (`brief`, ciorna compusă din răspunsuri și materiale), problemele de completitudine și
  intrarea din Creier în care a fost trimis.
- `onboarding_intrebari`: fiecare întrebare pusă (din interviul fix sau de clarificare, generată de model), cu
  răspunsul ei. Întrebările de clarificare stau imediat după întrebarea-părinte (`ordine`).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE onboarding_sesiuni (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            stare text NOT NULL DEFAULT 'interviu'
                CHECK (stare IN ('interviu', 'compune', 'brief_gata', 'trimis')),
            brief jsonb CHECK (brief IS NULL OR jsonb_typeof(brief) = 'object'),
            brief_probleme jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(brief_probleme) = 'array'),
            brief_intrare_id uuid,
            flux_id text,
            amanat_pana timestamptz,
            creat_de uuid REFERENCES utilizatori (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX onboarding_sesiuni_deschisa ON onboarding_sesiuni (tenant_id) WHERE stare <> 'trimis'"
    )
    activeaza_rls_tenant(op.execute, "onboarding_sesiuni", drepturi="SELECT, INSERT, UPDATE")
    op.execute(
        """CREATE TABLE onboarding_intrebari (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            sesiune_id uuid NOT NULL REFERENCES onboarding_sesiuni (id),
            ordine integer NOT NULL CHECK (ordine > 0),
            tip text NOT NULL CHECK (tip IN ('intrebare', 'clarificare')),
            cod text NOT NULL CHECK (cod ~ '^[a-z][a-z0-9_]{1,40}$'),
            camp text NOT NULL CHECK (camp ~ '^[a-z][a-z0-9_]{1,40}$'),
            text_intrebare text NOT NULL CHECK (length(text_intrebare) BETWEEN 3 AND 1000),
            parinte_id uuid REFERENCES onboarding_intrebari (id),
            generata_de text NOT NULL DEFAULT 'date' CHECK (generata_de IN ('date', 'model', 'sablon')),
            raspuns text CHECK (raspuns IS NULL OR length(raspuns) <= 6000),
            raspuns_la timestamptz,
            raspuns_de uuid REFERENCES utilizatori (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (sesiune_id, ordine),
            CHECK ((tip = 'clarificare') = (parinte_id IS NOT NULL))
        )"""
    )
    activeaza_rls_tenant(op.execute, "onboarding_intrebari", drepturi="SELECT, INSERT, UPDATE")


def downgrade() -> None:
    op.execute("DROP TABLE onboarding_intrebari")
    op.execute("DROP TABLE onboarding_sesiuni")
