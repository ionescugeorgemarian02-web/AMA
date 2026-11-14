"""Curba de retenție a clipurilor (F10.2, K2, docs/03: doar YouTube o dă prin API)

Revizia: 0058
Anterioara: 0057

- `curbe_retentie`: ultima curbă citită pentru un clip publicat, un rând pe (livrabil, canal). `puncte` e o
  listă de perechi `[poziție, retenție]`: poziția în clip între 0 și 1, retenția ca parte din cei care au
  pornit clipul (poate trece de 1 când un pasaj e revăzut). Curba se recitește la 72 de ore, 7 și 28 de zile
  și o înlocuiește pe cea veche (datele platformei se completează în timp).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE curbe_retentie (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            canal text NOT NULL CHECK (canal ~ '^[a-z][a-z0-9_]{1,39}$'),
            id_extern text NOT NULL CHECK (length(id_extern) BETWEEN 1 AND 300),
            interval text NOT NULL CHECK (interval IN ('1h', '24h', '72h', '7z', '28z')),
            puncte jsonb NOT NULL CHECK (jsonb_typeof(puncte) = 'array' AND jsonb_array_length(puncte) BETWEEN 10 AND 1000),
            citit_la timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT curbe_retentie_unic UNIQUE (tenant_id, livrabil_id, canal)
        )"""
    )
    activeaza_rls_tenant(op.execute, "curbe_retentie")


def downgrade() -> None:
    op.execute("DROP TABLE curbe_retentie")
