"""Conținut: brieful fiecărui livrabil (F6.2, D5, docs/13 §13.2)

Revizia: 0035
Anterioara: 0034

- `briefuri`: scop, public, mesaj unic, fapte permise (doar din pachetul de context, cu id și versiune), format, apel la
  acțiune, legat de pachetul din care s-a scris. Unul pe livrabil; nu se modifică (doar adăugare).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE briefuri (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid NOT NULL UNIQUE REFERENCES livrabile (id),
            pachet_id uuid,
            continut jsonb NOT NULL CHECK (jsonb_typeof(continut -> 'fapte_permise') = 'array'),
            model text,
            creat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute(
        """CREATE FUNCTION briefuri_protejeaza() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.tenant_id IS DISTINCT FROM (SELECT tenant_id FROM livrabile WHERE id = NEW.livrabil_id) THEN
                RAISE EXCEPTION 'brieful trebuie să aibă clientul livrabilului' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER briefuri_protejat BEFORE INSERT ON briefuri "
        "FOR EACH ROW EXECUTE FUNCTION briefuri_protejeaza()"
    )
    activeaza_rls_tenant(op.execute, "briefuri", drepturi="SELECT, INSERT")


def downgrade() -> None:
    op.execute("DROP TABLE briefuri")
    op.execute("DROP FUNCTION briefuri_protejeaza()")
