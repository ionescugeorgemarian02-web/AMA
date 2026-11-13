"""Conținut: variantele de hook ale unui livrabil și alegerea lor (F6.3, E1, docs/13 §13.4)

Revizia: 0036
Anterioara: 0035

- `variante_hook`: 3–5 deschideri propuse de generatorul de hook-uri, fiecare cu tiparul ei (eticheta alimentează alegerea
  adaptivă din F11), scorul determinist și cea aleasă (una pe livrabil). Doar adăugare; `ales` se setează o dată.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE variante_hook (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            nr integer NOT NULL CHECK (nr BETWEEN 1 AND 5),
            text text NOT NULL CHECK (length(text) BETWEEN 3 AND 300),
            tipar text NOT NULL CHECK (tipar ~ '^[a-z_]{3,30}$'),
            scor integer NOT NULL,
            probleme jsonb NOT NULL DEFAULT '[]',
            ales boolean NOT NULL DEFAULT false,
            model text,
            creat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (livrabil_id, nr)
        )"""
    )
    op.execute("CREATE UNIQUE INDEX variante_hook_aleasa ON variante_hook (livrabil_id) WHERE ales")
    op.execute(
        """CREATE FUNCTION variante_hook_protejeaza() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.tenant_id IS DISTINCT FROM (SELECT tenant_id FROM livrabile WHERE id = NEW.livrabil_id) THEN
                RAISE EXCEPTION 'varianta trebuie să aibă clientul livrabilului' USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'UPDATE' AND ((NEW.livrabil_id, NEW.nr, NEW.text, NEW.tipar, NEW.scor, NEW.tenant_id)
                IS DISTINCT FROM (OLD.livrabil_id, OLD.nr, OLD.text, OLD.tipar, OLD.scor, OLD.tenant_id) OR OLD.ales) THEN
                RAISE EXCEPTION 'varianta nu se schimbă; se alege o singură dată' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER variante_hook_protejat BEFORE INSERT OR UPDATE ON variante_hook "
        "FOR EACH ROW EXECUTE FUNCTION variante_hook_protejeaza()"
    )
    activeaza_rls_tenant(op.execute, "variante_hook", drepturi="SELECT, INSERT, UPDATE")


def downgrade() -> None:
    op.execute("DROP TABLE variante_hook")
    op.execute("DROP FUNCTION variante_hook_protejeaza()")
