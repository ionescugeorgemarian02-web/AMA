"""Folosirile activelor, cu licența cerută de bază (F8.4, docs/14 §14.3, G7)

Revizia: 0049
Anterioara: 0048

- `folosiri_active`: unde a fost folosit un activ (scopul și obiectul: o randare, o compoziție).
- Declanșatorul `folosire_cere_licenta` refuză rândul dacă activul nu are licență cu statutul `verificata`:
  niciun activ nu se folosește fără licență înregistrată, oricine ar scrie în tabel.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE folosiri_active (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            activ_id uuid NOT NULL REFERENCES active (id),
            scop text NOT NULL CHECK (scop ~ '^[a-z_]{3,40}$'),
            obiect_id uuid,
            creat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX folosiri_active_activ ON folosiri_active (activ_id)")
    op.execute(
        """CREATE FUNCTION folosire_cere_licenta() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE statut text;
        BEGIN
            SELECT licenta->>'statut' INTO statut FROM active WHERE id = NEW.activ_id AND tenant_id = NEW.tenant_id;
            IF statut IS DISTINCT FROM 'verificata' THEN
                RAISE EXCEPTION 'activul % nu are licență înregistrată', NEW.activ_id USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER folosire_cere_licenta BEFORE INSERT OR UPDATE ON folosiri_active "
        "FOR EACH ROW EXECUTE FUNCTION folosire_cere_licenta()"
    )
    activeaza_rls_tenant(op.execute, "folosiri_active", drepturi="SELECT, INSERT")


def downgrade() -> None:
    op.execute("DROP TABLE folosiri_active")
    op.execute("DROP FUNCTION folosire_cere_licenta()")
