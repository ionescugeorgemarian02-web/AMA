"""FT.1: jurnalul unic de urme (trasabilitate totală), doar adăugare, cu RLS

Revizia: 0076
Anterioara: 0075
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None

AUTH = "(SELECT ama_auth())"
AGENTIE = "(SELECT ama_agency())"
TENANT = "(SELECT ama_tenant_id())"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE urme (
            id uuid PRIMARY KEY,
            la timestamptz NOT NULL DEFAULT now(),
            tenant_id uuid,
            corelare_id text NOT NULL CHECK (length(corelare_id) BETWEEN 1 AND 100),
            cauza_id uuid,
            componenta text NOT NULL CHECK (length(componenta) BETWEEN 1 AND 60),
            actiune text NOT NULL CHECK (length(actiune) BETWEEN 1 AND 120),
            actor text NOT NULL DEFAULT 'sistem' CHECK (length(actor) BETWEEN 1 AND 100),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 500),
            rezultat text NOT NULL CHECK (rezultat IN ('ok', 'esec', 'respins', 'amanat', 'blocat', 'info')),
            cod text NOT NULL DEFAULT '' CHECK (length(cod) <= 100),
            cost numeric(14, 6) NOT NULL DEFAULT 0 CHECK (cost >= 0),
            unitate_cost text NOT NULL DEFAULT '' CHECK (unitate_cost IN ('', 'usd_umbra', 'lei', 'usd')),
            durata_ms integer CHECK (durata_ms >= 0),
            obiect_tip text,
            obiect_id text,
            intrari jsonb NOT NULL DEFAULT '{}'::jsonb,
            iesiri jsonb NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    op.execute("CREATE INDEX urme_la ON urme (la DESC)")
    op.execute("CREATE INDEX urme_corelare ON urme (corelare_id, la)")
    op.execute("CREATE INDEX urme_componenta ON urme (componenta, la DESC)")
    op.execute("CREATE INDEX urme_tenant ON urme (tenant_id, la DESC)")
    op.execute("CREATE INDEX urme_cauza ON urme (cauza_id) WHERE cauza_id IS NOT NULL")
    op.execute("CREATE INDEX urme_obiect ON urme (obiect_id) WHERE obiect_id IS NOT NULL")
    op.execute(
        "CREATE TRIGGER urme_fara_modificari BEFORE UPDATE OR DELETE ON urme "
        "FOR EACH ROW EXECUTE FUNCTION ama_jurnal_doar_adaugare()"
    )
    op.execute(
        "CREATE TRIGGER urme_fara_golire BEFORE TRUNCATE ON urme "
        "FOR EACH STATEMENT EXECUTE FUNCTION ama_jurnal_doar_adaugare()"
    )
    activeaza_rls(op.execute, "urme")
    op.execute(f"CREATE POLICY urme_citire ON urme FOR SELECT USING (tenant_id = {TENANT} OR {AGENTIE})")
    op.execute(
        f"CREATE POLICY urme_adaugare ON urme FOR INSERT WITH CHECK (tenant_id = {TENANT} OR {AGENTIE} OR {AUTH})"
    )
    op.execute("REVOKE ALL ON urme FROM ama_app")
    op.execute("GRANT SELECT, INSERT ON urme TO ama_app")


def downgrade() -> None:
    op.execute("DROP TABLE urme")
