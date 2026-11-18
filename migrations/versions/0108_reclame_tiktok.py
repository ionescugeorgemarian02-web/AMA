"""Reclamele pe TikTok (F16.6)

Revizia: 0108
Anterioara: 0107

- `reclame_conturi.platforma` acceptă și `tiktok` (contul de reclame TikTok for Business, prin același gardian de
  buget F13.5). Constrângerea se lărgește; downgrade-ul o îngustează la loc (refuză dacă există conturi TikTok).
"""

from alembic import op

revision = "0108"
down_revision = "0107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE reclame_conturi DROP CONSTRAINT reclame_conturi_platforma_check")
    op.execute(
        "ALTER TABLE reclame_conturi ADD CONSTRAINT reclame_conturi_platforma_check "
        "CHECK (platforma IN ('meta', 'google', 'tiktok'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE reclame_conturi DROP CONSTRAINT reclame_conturi_platforma_check")
    op.execute(
        "ALTER TABLE reclame_conturi ADD CONSTRAINT reclame_conturi_platforma_check "
        "CHECK (platforma IN ('meta', 'google'))"
    )
