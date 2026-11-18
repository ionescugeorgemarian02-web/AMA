"""Asistentul de suport din portal (F12.10, docs/19 §19.2)

Revizia: 0103
Anterioara: 0102

- `portal_suport`: întrebările clienților către asistent, categoria, răspunsul dat din datele clientului sau
  escaladarea la proprietar (facturare, reclamații, ce nu știe). Date ale clientului: RLS pe `tenant_id`;
  agenția le vede pe toate (proprietarul preia escaladările).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE portal_suport (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            utilizator_id uuid REFERENCES utilizatori (id),
            intrebare text NOT NULL CHECK (length(intrebare) BETWEEN 2 AND 1000),
            categorie text NOT NULL CHECK (categorie IN ('livrabile', 'cont', 'magazin', 'facturare', 'reclamatie', 'altceva')),
            raspuns text NOT NULL DEFAULT '' CHECK (length(raspuns) <= 4000),
            escaladat boolean NOT NULL,
            preluat_la timestamptz,
            la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute(
        "CREATE INDEX portal_suport_escaladate ON portal_suport (la) WHERE escaladat AND preluat_la IS NULL"
    )
    activeaza_rls_tenant(op.execute, "portal_suport")


def downgrade() -> None:
    op.execute("DROP TABLE portal_suport")
