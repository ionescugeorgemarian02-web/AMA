"""Întrerupătorul global (F2.4): oprirea producției noi și canalul „sistem”

Revizia: 0008
Anterioara: 0007

`opriri` primește tipul `productie` (oprirea producției noi, pusă de întrerupătorul din 7.3 sau de om) și canalul
`sistem` (întrerupătorul o oprește singur; repornirea rămâne doar a omului, cu canalul `panou` sau `telegram`).
Nicio tabelă nouă: contoarele și bugetele per livrabil sunt în `livrabile` (0007).
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE opriri DROP CONSTRAINT opriri_tip_check")
    op.execute(
        "ALTER TABLE opriri ADD CONSTRAINT opriri_tip_check CHECK "
        "(tip IN ('publicare', 'productie', 'reclame', 'invatare', 'apeluri_platite', 'client'))"
    )
    op.execute("ALTER TABLE opriri DROP CONSTRAINT opriri_canal_check")
    op.execute(
        "ALTER TABLE opriri ADD CONSTRAINT opriri_canal_check CHECK (canal IN ('panou', 'telegram', 'sistem'))"
    )


def downgrade() -> None:
    # Starea curentă a opririi producției se pierde la coborâre; istoricul rămâne în jurnalul de audit.
    op.execute("DELETE FROM opriri WHERE tip = 'productie' OR canal = 'sistem'")
    op.execute("ALTER TABLE opriri DROP CONSTRAINT opriri_canal_check")
    op.execute("ALTER TABLE opriri ADD CONSTRAINT opriri_canal_check CHECK (canal IN ('panou', 'telegram'))")
    op.execute("ALTER TABLE opriri DROP CONSTRAINT opriri_tip_check")
    op.execute(
        "ALTER TABLE opriri ADD CONSTRAINT opriri_tip_check CHECK "
        "(tip IN ('publicare', 'reclame', 'invatare', 'apeluri_platite', 'client'))"
    )
