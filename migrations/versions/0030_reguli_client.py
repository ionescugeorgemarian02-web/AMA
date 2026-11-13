"""Validare: regulile pe client (F5.4, docs/09 §9.7)

Revizia: 0030
Anterioara: 0029

- `reguli_client`: regulile proprii ale unui client (pe lângă pachetele din `rulepacks/`). Fiecare rând este o VERSIUNE a unei
  reguli (definiția completă, cu exemplele ei, validată de aplicație la scriere); doar adăugare: o schimbare este o versiune
  nouă, o retragere este o versiune cu `retrasa`. Autorul uman este obligatoriu (`creat_de NOT NULL`): regulile se schimbă doar
  prin revizuire umană, niciun cod automat nu le scrie.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE reguli_client (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            regula_id text NOT NULL CHECK (regula_id ~ '^[a-z][a-z0-9-]{2,60}$'),
            versiune integer NOT NULL CHECK (versiune >= 1),
            definitie jsonb NOT NULL CHECK (jsonb_typeof(definitie) = 'object'),
            retrasa boolean NOT NULL DEFAULT false,
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 500),
            creat_de uuid NOT NULL REFERENCES utilizatori (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, regula_id, versiune)
        )"""
    )
    op.execute("CREATE INDEX reguli_client_client ON reguli_client (tenant_id, regula_id, versiune DESC)")
    op.execute(
        "CREATE TRIGGER reguli_client_fara_modificari BEFORE UPDATE OR DELETE ON reguli_client "
        "FOR EACH ROW EXECUTE FUNCTION ama_jurnal_doar_adaugare()"
    )
    op.execute(
        "CREATE TRIGGER reguli_client_fara_golire BEFORE TRUNCATE ON reguli_client "
        "FOR EACH STATEMENT EXECUTE FUNCTION ama_jurnal_doar_adaugare()"
    )
    activeaza_rls_tenant(op.execute, "reguli_client", drepturi="SELECT, INSERT")


def downgrade() -> None:
    op.execute("DROP TABLE reguli_client")
