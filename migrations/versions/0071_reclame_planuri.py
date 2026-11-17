"""Reclame: planurile media (F13.3, I1, docs/16 §16.3–16.4)

Revizia: 0071
Anterioara: 0070

- `reclame_planuri`: planul media al unui cont (structură, public, împărțirea bugetului, matricea de creativuri,
  măsurare, plafoane, criterii de oprire), cu problemele găsite de verificare. Un plan aprobat nu se mai schimbă.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE reclame_planuri (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            cont_id uuid NOT NULL REFERENCES reclame_conturi (id),
            continut jsonb NOT NULL CHECK (jsonb_typeof(continut) = 'object'),
            probleme jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(probleme) = 'array'),
            stare text NOT NULL DEFAULT 'propus' CHECK (stare IN ('propus', 'aprobat', 'respins')),
            creat_la timestamptz NOT NULL DEFAULT now(),
            decis_de uuid REFERENCES utilizatori (id),
            decis_la timestamptz,
            CHECK ((stare = 'propus') = (decis_la IS NULL)),
            CHECK (stare <> 'aprobat' OR probleme = '[]'::jsonb)
        )"""
    )
    op.execute(
        """CREATE FUNCTION reclame_planuri_protejeaza() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.stare <> 'propus' THEN
                RAISE EXCEPTION 'un plan aprobat sau respins nu se mai schimbă' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER reclame_planuri_protejat BEFORE UPDATE ON reclame_planuri "
        "FOR EACH ROW EXECUTE FUNCTION reclame_planuri_protejeaza()"
    )
    activeaza_rls_tenant(op.execute, "reclame_planuri")


def downgrade() -> None:
    op.execute("DROP TABLE reclame_planuri")
    op.execute("DROP FUNCTION reclame_planuri_protejeaza()")
