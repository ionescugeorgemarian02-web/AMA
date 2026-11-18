"""Canalele noi de publicare (F16.2): Pinterest, Google Business Profile, Threads

Revizia: 0104
Anterioara: 0103

- `aprobari_api`: aprobările aplicației agenției pentru cele trei canale, pornite în modul de test (doar conturile
  agenției), ca celelalte. Fără rând, canalul ar părea că nu cere aprobare și ar trece pe automat.
"""

from alembic import op

revision = "0104"
down_revision = "0103"
branch_labels = None
depends_on = None

APROBARI = (("pinterest", "publicare"), ("google", "business"), ("meta", "threads"))


def upgrade() -> None:
    op.execute("SELECT set_config('app.agency', '1', true)")  # RLS e forțat și pentru proprietarul migrării
    for platforma, permisiune in APROBARI:
        op.execute(
            "INSERT INTO aprobari_api (platforma, permisiune, stare) "
            f"VALUES ('{platforma}', '{permisiune}', 'in_test') ON CONFLICT DO NOTHING"
        )


def downgrade() -> None:
    op.execute("SELECT set_config('app.agency', '1', true)")
    for platforma, permisiune in APROBARI:
        op.execute(
            f"DELETE FROM aprobari_api WHERE platforma = '{platforma}' AND permisiune = '{permisiune}'"
        )
