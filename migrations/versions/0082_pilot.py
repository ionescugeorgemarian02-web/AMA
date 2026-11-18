"""Pilotul cu trei clienți (F15.5, docs/25 §25.6): înscrierea, feedback-ul săptămânal, raportul săptămânal

Revizia: 0082
Anterioara: 0081

- `pilot_clienti`: un client în pilot (L1, prețul de pilot în bani, începutul, numărul de săptămâni, starea).
- `pilot_feedback`: întâlnirea săptămânală (satisfacția 1–5, minutele de om, fricțiunile), una pe săptămână.
- `pilot_rapoarte`: raportul săptămânal calculat din urme (aprobarea din prima, incidentele critice, minutele).
Toate trei sunt date de client: le vede doar clientul și agenția (RLS pe `tenant_id`).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE pilot_clienti (
            tenant_id uuid PRIMARY KEY REFERENCES clienti (id),
            inceput date NOT NULL,
            saptamani integer NOT NULL DEFAULT 4 CHECK (saptamani BETWEEN 1 AND 26),
            pret_lunar_bani integer NOT NULL CHECK (pret_lunar_bani >= 0),
            stare text NOT NULL DEFAULT 'activ' CHECK (stare IN ('activ', 'incheiat', 'oprit')),
            note text NOT NULL DEFAULT '' CHECK (length(note) <= 2000),
            creat_la timestamptz NOT NULL DEFAULT now(),
            creat_de uuid
        )"""
    )
    activeaza_rls_tenant(op.execute, "pilot_clienti")
    op.execute(
        """CREATE TABLE pilot_feedback (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            saptamana date NOT NULL CHECK (extract(isodow FROM saptamana) = 1),
            satisfactie integer NOT NULL CHECK (satisfactie BETWEEN 1 AND 5),
            minute_om integer NOT NULL DEFAULT 0 CHECK (minute_om BETWEEN 0 AND 10000),
            frictiuni text NOT NULL DEFAULT '' CHECK (length(frictiuni) <= 4000),
            creat_la timestamptz NOT NULL DEFAULT now(),
            creat_de uuid,
            UNIQUE (tenant_id, saptamana)
        )"""
    )
    activeaza_rls_tenant(op.execute, "pilot_feedback")
    op.execute(
        """CREATE TABLE pilot_rapoarte (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            saptamana date NOT NULL CHECK (extract(isodow FROM saptamana) = 1),
            continut jsonb NOT NULL CHECK (jsonb_typeof(continut) = 'object'),
            generat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, saptamana)
        )"""
    )
    activeaza_rls_tenant(op.execute, "pilot_rapoarte")


def downgrade() -> None:
    op.execute("DROP TABLE pilot_rapoarte")
    op.execute("DROP TABLE pilot_feedback")
    op.execute("DROP TABLE pilot_clienti")
