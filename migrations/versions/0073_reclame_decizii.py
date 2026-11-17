"""Reclame: înregistrările de decizie ale Strategului și ale Consiliului (F13.6, docs/07 §7.7, docs/16 §16.9)

Revizia: 0073
Anterioara: 0072

- `reclame_decizii`: ce s-a văzut (cifrele ferestrei), ce s-a decis (una din cele patru ieșiri sau „așteaptă”),
  de ce, alternativele (la pivot și la oprire: trei ipoteze, testate pe 20% din buget), ce se așteaptă și când se
  verifică. O înregistrare nu se mai schimbă după ce a fost scrisă.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE reclame_decizii (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            cont_id uuid NOT NULL REFERENCES reclame_conturi (id),
            campanie_id uuid REFERENCES reclame_campanii (id),
            sursa text NOT NULL CHECK (sursa IN ('strateg', 'consiliu')),
            de_la date NOT NULL,
            pana_la date NOT NULL,
            observat jsonb NOT NULL CHECK (jsonb_typeof(observat) = 'object'),
            iesire text NOT NULL CHECK (iesire IN ('continua', 'ajusteaza', 'pivoteaza', 'opreste', 'asteapta')),
            motiv text NOT NULL CHECK (length(motiv) BETWEEN 3 AND 1000),
            alternative jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(alternative) = 'array'),
            asteptat text NOT NULL DEFAULT '' CHECK (length(asteptat) <= 500),
            verificare_la date NOT NULL,
            propuneri jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(propuneri) = 'array'),
            model text,
            creat_la timestamptz NOT NULL DEFAULT now(),
            CHECK (de_la <= pana_la AND pana_la < verificare_la)
        )"""
    )
    op.execute("CREATE INDEX reclame_decizii_cont ON reclame_decizii (cont_id, creat_la)")
    activeaza_rls_tenant(op.execute, "reclame_decizii", drepturi="SELECT, INSERT")


def downgrade() -> None:
    op.execute("DROP TABLE reclame_decizii")
