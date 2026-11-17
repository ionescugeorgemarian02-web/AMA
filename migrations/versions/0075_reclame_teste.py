"""Reclame: testele de creative (F13.9, I4, docs/16 §16.6)

Revizia: 0075
Anterioara: 0074

- `reclame_teste`: testul unei campanii de test (o singură variabilă, buget egal pe variante), cu probabilitatea
  fiecărei variante de a fi cea mai bună, câștigătoarea și cifrele variantelor (memoria de performanță).
- `reclame_propuneri.tip` primește `adauga_anunt`: câștigătoarea trece în campania de scalare.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None

TIPURI_VECHI = "('creeaza', 'stare', 'buget', 'stare_anunt')"
TIPURI_NOI = "('creeaza', 'stare', 'buget', 'stare_anunt', 'adauga_anunt')"


def upgrade() -> None:
    op.execute("ALTER TABLE reclame_propuneri DROP CONSTRAINT reclame_propuneri_tip_check")
    op.execute(
        f"ALTER TABLE reclame_propuneri ADD CONSTRAINT reclame_propuneri_tip_check CHECK (tip IN {TIPURI_NOI})"
    )
    op.execute(
        """CREATE TABLE reclame_teste (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            campanie_id uuid NOT NULL REFERENCES reclame_campanii (id),
            variabila text NOT NULL CHECK (variabila IN ('hook', 'oferta', 'format', 'public')),
            stare text NOT NULL DEFAULT 'in_curs' CHECK (stare IN ('in_curs', 'incheiat', 'oprit')),
            castigator_anunt_id uuid REFERENCES reclame_anunturi (id),
            variante jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(variante) = 'array'),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 500),
            inceput_la timestamptz NOT NULL DEFAULT now(),
            incheiat_la timestamptz,
            CHECK ((stare = 'in_curs') = (incheiat_la IS NULL)),
            CHECK (stare <> 'incheiat' OR castigator_anunt_id IS NOT NULL)
        )"""
    )
    op.execute("CREATE UNIQUE INDEX reclame_teste_unul ON reclame_teste (campanie_id)")
    activeaza_rls_tenant(op.execute, "reclame_teste")


def downgrade() -> None:
    op.execute("DROP TABLE reclame_teste")
    op.execute("DELETE FROM reclame_propuneri WHERE tip = 'adauga_anunt'")
    op.execute("ALTER TABLE reclame_propuneri DROP CONSTRAINT reclame_propuneri_tip_check")
    op.execute(
        f"ALTER TABLE reclame_propuneri ADD CONSTRAINT reclame_propuneri_tip_check CHECK (tip IN {TIPURI_VECHI})"
    )
