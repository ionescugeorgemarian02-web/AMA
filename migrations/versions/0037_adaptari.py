"""Conținut: adaptările unei idei pe canale (F6.5, E10, docs/05, docs/15 §15.4)

Revizia: 0037
Anterioara: 0036

- `adaptari`: legătura dintre livrabilul-sursă (postarea validată) și livrabilul nou, scris nativ pentru alt canal. O
  adaptare pe (sursă, canal); doar adăugare.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE adaptari (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            sursa_livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            livrabil_id uuid NOT NULL UNIQUE REFERENCES livrabile (id),
            canal text NOT NULL CHECK (canal ~ '^[a-z][a-z0-9_]{1,39}$'),
            model text,
            creat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (sursa_livrabil_id, canal),
            CHECK (sursa_livrabil_id <> livrabil_id)
        )"""
    )
    op.execute(
        """CREATE FUNCTION adaptari_protejeaza() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.tenant_id IS DISTINCT FROM (SELECT tenant_id FROM livrabile WHERE id = NEW.sursa_livrabil_id)
               OR NEW.tenant_id IS DISTINCT FROM (SELECT tenant_id FROM livrabile WHERE id = NEW.livrabil_id) THEN
                RAISE EXCEPTION 'adaptarea trebuie să aibă clientul livrabilelor' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER adaptari_protejat BEFORE INSERT ON adaptari FOR EACH ROW EXECUTE FUNCTION adaptari_protejeaza()"
    )
    activeaza_rls_tenant(op.execute, "adaptari", drepturi="SELECT, INSERT")


def downgrade() -> None:
    op.execute("DROP TABLE adaptari")
    op.execute("DROP FUNCTION adaptari_protejeaza()")
