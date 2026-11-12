"""Gateway de modele: semnalele gărzilor în jurnalul de apeluri (F3.9, docs/08 §8.9, docs/12 §12.8)

Revizia: 0017
Anterioara: 0016

- `gateway_apeluri.semnale`: lista semnalelor unui apel (date personale mascate, pe tip, fără valori; tentative de injecție
  găsite în conținutul extern, cu codul tiparului și sursa, fără text). Jurnalul rămâne doar-adăugare.
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE gateway_apeluri ADD COLUMN semnale jsonb NOT NULL DEFAULT '[]'::jsonb "
        "CHECK (jsonb_typeof(semnale) = 'array' AND octet_length(semnale::text) <= 4096)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE gateway_apeluri DROP COLUMN semnale")
