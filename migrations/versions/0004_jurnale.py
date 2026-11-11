"""Jurnal de audit și jurnal de evenimente (doar adăugări), cu RLS

Revizia: 0004
Anterioara: 0003
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

AUTH = "(SELECT ama_auth())"
AGENTIE = "(SELECT ama_agency())"
TENANT = "(SELECT ama_tenant_id())"
JURNALE = ("jurnal_audit", "jurnal_evenimente")


def upgrade() -> None:
    op.execute(
        """CREATE TABLE jurnal_audit (
            id uuid PRIMARY KEY,
            creat_la timestamptz NOT NULL DEFAULT now(),
            tenant_id uuid REFERENCES clienti (id),
            utilizator_id uuid REFERENCES utilizatori (id),
            actor_tip text NOT NULL DEFAULT 'utilizator' CHECK (actor_tip IN ('utilizator', 'sistem', 'cli', 'anonim')),
            actiune text NOT NULL CHECK (length(actiune) BETWEEN 1 AND 100),
            obiect_tip text,
            obiect_id text,
            rezultat text NOT NULL DEFAULT 'ok' CHECK (rezultat IN ('ok', 'esec', 'refuzat')),
            ip text,
            corelare_id text,
            detalii jsonb NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    op.execute(
        """CREATE TABLE jurnal_evenimente (
            id uuid PRIMARY KEY,
            creat_la timestamptz NOT NULL DEFAULT now(),
            tenant_id uuid REFERENCES clienti (id),
            utilizator_id uuid REFERENCES utilizatori (id),
            tip text NOT NULL CHECK (length(tip) BETWEEN 1 AND 100),
            sursa text NOT NULL,
            obiect_tip text,
            obiect_id text,
            corelare_id text,
            date jsonb NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    op.execute(
        """CREATE FUNCTION ama_jurnal_doar_adaugare() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'jurnalul % este doar pentru adaugare (% refuzat)', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'integrity_constraint_violation';
        END $$"""
    )
    for t in JURNALE:
        op.execute(f"CREATE INDEX {t}_tenant ON {t} (tenant_id, creat_la DESC)")
        op.execute(f"CREATE INDEX {t}_utilizator ON {t} (utilizator_id, creat_la DESC)")
        op.execute(
            f"CREATE TRIGGER {t}_fara_modificari BEFORE UPDATE OR DELETE ON {t} "
            f"FOR EACH ROW EXECUTE FUNCTION ama_jurnal_doar_adaugare()"
        )
        op.execute(
            f"CREATE TRIGGER {t}_fara_golire BEFORE TRUNCATE ON {t} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION ama_jurnal_doar_adaugare()"
        )
        activeaza_rls(op.execute, t)
        # Citire: clientul își vede rândurile; intrările fără client (tenant_id NULL) doar agenția.
        op.execute(f"CREATE POLICY {t}_citire ON {t} FOR SELECT USING (tenant_id = {TENANT} OR {AGENTIE})")
        # Scriere: la fel; fluxul de autentificare (fără context de client încă) poate doar adăuga.
        op.execute(
            f"CREATE POLICY {t}_adaugare ON {t} FOR INSERT WITH CHECK (tenant_id = {TENANT} OR {AGENTIE} OR {AUTH})"
        )
        op.execute(f"GRANT SELECT, INSERT ON {t} TO ama_app")  # fără UPDATE/DELETE/TRUNCATE


def downgrade() -> None:
    for t in JURNALE:
        op.execute(f"DROP TABLE {t}")
    op.execute("DROP FUNCTION ama_jurnal_doar_adaugare()")
