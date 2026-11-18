"""Vocea proprie antrenată (F16.4, docs/14 §14.2, ADR-10)

Revizia: 0106
Anterioara: 0105

- `voce_consimtaminte`: acordul scris al vorbitorului (amprenta documentului semnat, scopurile, revocarea). Fără
  acord valabil nu se antrenează și nu se sintetizează nimic.
- `voce_modele`: modelul antrenat o singură dată din înregistrările vorbitorului, legat de acord; retras la revocare.
Date ale clientului: RLS pe `tenant_id`. Rândurile nu se șterg (dovada acordului), doar se revocă.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0106"
down_revision = "0105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE voce_consimtaminte (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            vorbitor text NOT NULL CHECK (length(vorbitor) BETWEEN 2 AND 120),
            document_sha256 text NOT NULL CHECK (document_sha256 ~ '^[0-9a-f]{64}$'),
            scopuri text[] NOT NULL CHECK (cardinality(scopuri) >= 1
                AND scopuri <@ ARRAY['continut_organic', 'reclame', 'raspunsuri']::text[]),
            acordat_la timestamptz NOT NULL DEFAULT now(),
            inregistrat_de uuid REFERENCES utilizatori (id),
            revocat_la timestamptz,
            motiv_revocare text NOT NULL DEFAULT '' CHECK (length(motiv_revocare) <= 500)
        )"""
    )
    activeaza_rls_tenant(op.execute, "voce_consimtaminte")
    op.execute(
        """CREATE TABLE voce_modele (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            consimtamant_id uuid NOT NULL REFERENCES voce_consimtaminte (id),
            stare text NOT NULL CHECK (stare IN ('gata', 'retras')),
            minute_inregistrate numeric(8, 2) NOT NULL CHECK (minute_inregistrate > 0),
            motor text NOT NULL CHECK (length(motor) BETWEEN 1 AND 60),
            model_ref text NOT NULL CHECK (length(model_ref) BETWEEN 1 AND 200),
            creat_la timestamptz NOT NULL DEFAULT now(),
            retras_la timestamptz
        )"""
    )
    activeaza_rls_tenant(op.execute, "voce_modele")


def downgrade() -> None:
    op.execute("DROP TABLE voce_modele")
    op.execute("DROP TABLE voce_consimtaminte")
