"""Limba conținutului clientului (F16.3)

Revizia: 0105
Anterioara: 0104

- `clienti.limba`: limba în care se scrie și se validează conținutul clientului (`ro` implicit, `en`). Coloană nouă
  cu valoare implicită: compatibilă cu versiunea anterioară.
"""

from alembic import op

revision = "0105"
down_revision = "0104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE clienti ADD COLUMN limba text NOT NULL DEFAULT 'ro' CHECK (limba IN ('ro', 'en'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE clienti DROP COLUMN limba")
