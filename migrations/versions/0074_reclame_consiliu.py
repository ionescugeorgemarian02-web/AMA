"""Reclame: dosarele de Consiliu (F13.7, docs/07 §7.6)

Revizia: 0074
Anterioara: 0073

- `reclame_dosare`: dosarul pregătit de platformă (cifre, context, opțiuni, întrebări precise), motivul apelului,
  modul de conectare (manual asistat sau API), starea (deschis, decis, amânat la plafonul lunar) și decizia
  structurată importată (alegerea, motivele, condițiile, ce se măsoară, acțiunile).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE reclame_dosare (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            cont_id uuid NOT NULL REFERENCES reclame_conturi (id),
            subiect text NOT NULL CHECK (length(subiect) BETWEEN 5 AND 200),
            motiv_apel text NOT NULL CHECK (length(motiv_apel) BETWEEN 10 AND 500),
            continut text NOT NULL CHECK (length(continut) BETWEEN 50 AND 30000),
            optiuni jsonb NOT NULL CHECK (jsonb_typeof(optiuni) = 'array'),
            mod text NOT NULL DEFAULT 'manual' CHECK (mod IN ('manual', 'api')),
            stare text NOT NULL DEFAULT 'deschis' CHECK (stare IN ('deschis', 'decis', 'amanat')),
            luna date NOT NULL CHECK (extract(day FROM luna) = 1),
            decizie jsonb,
            decizie_id uuid REFERENCES reclame_decizii (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            decis_de uuid REFERENCES utilizatori (id),
            decis_la timestamptz,
            CHECK ((stare = 'decis') = (decizie IS NOT NULL))
        )"""
    )
    op.execute("CREATE INDEX reclame_dosare_luna ON reclame_dosare (luna, stare)")
    activeaza_rls_tenant(op.execute, "reclame_dosare")


def downgrade() -> None:
    op.execute("DROP TABLE reclame_dosare")
