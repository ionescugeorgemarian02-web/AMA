"""Licența și generarea activelor; audio în bibliotecă (F8.1, docs/14 §14.3–14.4, ADR-10)

Revizia: 0047
Anterioara: 0046

- `active.categorie` acceptă și `audio` (narațiuni sintetizate, muzică, efecte);
- `active.licenta` (jsonb): statutul drepturilor (de ex. profilul vocii și statutul licenței ei);
- `active.generare` (jsonb): cum a fost produs activul (motor, model, prompt, sămânță).
"""

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE active DROP CONSTRAINT active_categorie_check")
    op.execute(
        "ALTER TABLE active ADD CONSTRAINT active_categorie_check "
        "CHECK (categorie IN ('foto', 'video', 'document', 'audio'))"
    )
    op.execute(
        "ALTER TABLE active ADD COLUMN licenta jsonb "
        "CHECK (licenta IS NULL OR jsonb_typeof(licenta) = 'object')"
    )
    op.execute(
        "ALTER TABLE active ADD COLUMN generare jsonb "
        "CHECK (generare IS NULL OR jsonb_typeof(generare) = 'object')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE active DROP COLUMN generare")
    op.execute("ALTER TABLE active DROP COLUMN licenta")
    op.execute("ALTER TABLE active DROP CONSTRAINT active_categorie_check")
    op.execute(
        "ALTER TABLE active ADD CONSTRAINT active_categorie_check "
        "CHECK (categorie IN ('foto', 'video', 'document')) NOT VALID"
    )
