"""Rezultate fracționare și clicuri de trafic indisponibile la citirile istorice."""

from alembic import op

revision = "0140"
down_revision = "0109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE reclame_rezultate ALTER rezultate TYPE double precision, "
        "ALTER rezultate DROP NOT NULL, ADD clicuri_trafic bigint CHECK (clicuri_trafic >= 0)"
    )


def downgrade() -> None:
    op.execute("UPDATE reclame_rezultate SET rezultate = 0 WHERE rezultate IS NULL")
    op.execute(
        "ALTER TABLE reclame_rezultate DROP clicuri_trafic, ALTER rezultate SET NOT NULL, "
        "ALTER rezultate TYPE integer USING round(rezultate)::integer"
    )
