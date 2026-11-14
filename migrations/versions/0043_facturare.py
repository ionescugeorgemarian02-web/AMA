"""Facturarea: abonamente, facturi, webhook-urile procesatorului (F7.6, docs/19 §19.5)

Revizia: 0043
Anterioara: 0042

- `abonamente`: planul clientului la procesatorul de plăți (`id_extern`), starea (`in_asteptare_plata`, `activ`,
  `restant` = plată eșuată, în perioada de grație, `suspendat`, `anulat`) și perioada plătită. Fără date de card.
- `facturi`: plățile reușite și eșuate raportate de procesator (idempotent pe `id_extern`).
- `plati_evenimente`: webhook-urile verificate, o singură dată pe eveniment (date ale agenției).
"""

from alembic import op

from app.db.rls import activeaza_rls, activeaza_rls_tenant

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE abonamente (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            plan text NOT NULL CHECK (plan ~ '^[a-z]{2,20}$'),
            suma integer NOT NULL CHECK (suma > 0),
            email_facturare text NOT NULL CHECK (length(email_facturare) BETWEEN 6 AND 254),
            stare text NOT NULL DEFAULT 'in_asteptare_plata'
                CHECK (stare IN ('in_asteptare_plata', 'activ', 'restant', 'suspendat', 'anulat')),
            id_extern text UNIQUE,
            jeton_hash text NOT NULL UNIQUE,
            perioada_pana_la timestamptz,
            restant_de_la timestamptz,
            suspendat_la timestamptz,
            creat_la timestamptz NOT NULL DEFAULT now(),
            CHECK (stare <> 'restant' OR restant_de_la IS NOT NULL)
        )"""
    )
    activeaza_rls_tenant(op.execute, "abonamente")
    op.execute(
        """CREATE TABLE facturi (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            abonament_id uuid NOT NULL REFERENCES abonamente (id),
            id_extern text NOT NULL UNIQUE,
            suma integer NOT NULL CHECK (suma >= 0),
            moneda text NOT NULL DEFAULT 'RON',
            stare text NOT NULL CHECK (stare IN ('platita', 'esuata')),
            perioada_de_la timestamptz NOT NULL,
            perioada_pana_la timestamptz NOT NULL,
            creat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    activeaza_rls_tenant(op.execute, "facturi", drepturi="SELECT, INSERT")
    op.execute(
        """CREATE TABLE plati_evenimente (
            id_extern text PRIMARY KEY CHECK (length(id_extern) <= 100),
            tip text NOT NULL,
            corp jsonb NOT NULL,
            rezultat text NOT NULL DEFAULT '',
            primit_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    activeaza_rls(op.execute, "plati_evenimente")
    op.execute(
        f"CREATE POLICY plati_evenimente_agentie ON plati_evenimente USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON plati_evenimente TO ama_app")


def downgrade() -> None:
    op.execute("DROP TABLE plati_evenimente")
    op.execute("DROP TABLE facturi")
    op.execute("DROP TABLE abonamente")
