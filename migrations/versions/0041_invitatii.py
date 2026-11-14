"""Portalul clientului: invitațiile de activare a contului (F7.3, docs/19 §19.2–19.3)

Revizia: 0041
Anterioara: 0040

- `invitatii`: linkul de activare primit de client (după plată sau de la agenție). Jetonul se ține doar ca SHA-256,
  expiră și se folosește o singură dată; la activare se creează utilizatorul de client cu parola aleasă de el.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE invitatii (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            email text NOT NULL CHECK (length(email) BETWEEN 6 AND 254),
            rol text NOT NULL CHECK (rol IN ('client_titular', 'client_aprobator', 'client_vizitator')),
            jeton_hash text NOT NULL UNIQUE,
            expira_la timestamptz NOT NULL,
            folosita_la timestamptz,
            utilizator_id uuid REFERENCES utilizatori (id),
            creat_de uuid REFERENCES utilizatori (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            CHECK ((folosita_la IS NULL) = (utilizator_id IS NULL))
        )"""
    )
    activeaza_rls_tenant(op.execute, "invitatii")


def downgrade() -> None:
    op.execute("DROP TABLE invitatii")
