"""FS.6 Câmpuri comerciale pentru conținut și reclame."""

from alembic import op

revision = "0124"
down_revision = "0123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE comert_produse ADD COLUMN detalii jsonb NOT NULL DEFAULT '{}'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE comert_produse DROP COLUMN detalii")
