"""Consimțământul pentru postarea directă pe TikTok (F9.6, docs/15 §15.1)

Revizia: 0055
Anterioara: 0054

- `publicare_consimtaminte`: consimțământul explicit al omului pentru o postare, după previzualizare (contul,
  clipul, legenda), cu vizibilitatea ALEASĂ de el și interacțiunile; o singură dată pe versiune și canal.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None

CANAL = "CHECK (canal ~ '^[a-z][a-z0-9_]{1,39}$')"


def upgrade() -> None:
    op.execute(
        f"""CREATE TABLE publicare_consimtaminte (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            versiune integer NOT NULL CHECK (versiune >= 1),
            canal text NOT NULL {CANAL},
            optiuni jsonb NOT NULL CHECK (jsonb_typeof(optiuni) = 'object' AND optiuni ? 'vizibilitate'),
            previzualizare jsonb NOT NULL DEFAULT '{{}}',
            dat_de uuid NOT NULL REFERENCES utilizatori (id),
            dat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (livrabil_id, versiune, canal)
        )"""
    )
    activeaza_rls_tenant(op.execute, "publicare_consimtaminte", drepturi="SELECT, INSERT")


def downgrade() -> None:
    op.execute("DROP TABLE publicare_consimtaminte")
