"""Conturi: clienți, utilizatori, apartenențe, alocări, cu RLS

Revizia: 0002
Anterioara: 0001
"""

from alembic import op

from app.db.rls import activeaza_rls, activeaza_rls_tenant

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

ROLURI_AGENTIE = "('proprietar', 'operator', 'analist')"
ROLURI_CLIENT = "('client_titular', 'client_aprobator', 'client_vizitator')"
AGENTIE = "(SELECT ama_agency())"
UTILIZATOR = "(SELECT ama_user_id())"
TENANT = "(SELECT ama_tenant_id())"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE clienti (
            id uuid PRIMARY KEY,
            nume text NOT NULL CHECK (length(btrim(nume)) BETWEEN 1 AND 200),
            stare text NOT NULL DEFAULT 'activ' CHECK (stare IN ('activ', 'suspendat', 'arhivat')),
            creat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            sters_la timestamptz
        )"""
    )
    op.execute(
        """CREATE TABLE utilizatori (
            id uuid PRIMARY KEY,
            email citext NOT NULL UNIQUE CHECK (length(email) BETWEEN 3 AND 254),
            nume_afisat text NOT NULL CHECK (length(btrim(nume_afisat)) BETWEEN 1 AND 200),
            parola_hash text NOT NULL,
            stare text NOT NULL DEFAULT 'activ' CHECK (stare IN ('activ', 'blocat')),
            creat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            sters_la timestamptz
        )"""
    )
    op.execute(
        f"""CREATE TABLE apartenente (
            id uuid PRIMARY KEY,
            utilizator_id uuid NOT NULL REFERENCES utilizatori (id),
            tenant_id uuid REFERENCES clienti (id),
            rol text NOT NULL,
            creat_la timestamptz NOT NULL DEFAULT now(),
            sters_la timestamptz,
            CONSTRAINT rol_si_client_coerente CHECK (
                (rol IN {ROLURI_AGENTIE} AND tenant_id IS NULL)
                OR (rol IN {ROLURI_CLIENT} AND tenant_id IS NOT NULL)
            )
        )"""
    )
    op.execute("CREATE UNIQUE INDEX apartenente_o_singura_activa ON apartenente (utilizator_id) WHERE sters_la IS NULL")
    op.execute("CREATE INDEX apartenente_tenant ON apartenente (tenant_id)")
    op.execute(
        """CREATE TABLE alocari (
            id uuid PRIMARY KEY,
            utilizator_id uuid NOT NULL REFERENCES utilizatori (id),
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            creat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE UNIQUE INDEX alocari_unica ON alocari (utilizator_id, tenant_id)")
    op.execute("CREATE INDEX alocari_tenant ON alocari (tenant_id)")

    # alocari: citește clientul, agenția și operatorul însuși; scrie doar agenția.
    activeaza_rls(op.execute, "alocari")
    op.execute(
        f"CREATE POLICY alocari_citire ON alocari FOR SELECT "
        f"USING (tenant_id = {TENANT} OR {AGENTIE} OR utilizator_id = {UTILIZATOR})"
    )
    for cmd in ("INSERT", "DELETE"):
        clauza = "WITH CHECK" if cmd == "INSERT" else "USING"
        op.execute(f"CREATE POLICY alocari_{cmd.lower()} ON alocari FOR {cmd} {clauza} ({AGENTIE})")
    op.execute("GRANT SELECT, INSERT, DELETE ON alocari TO ama_app")

    # clienti: vede clientul curent, agenția și clienții alocați operatorului; scrie doar agenția.
    activeaza_rls(op.execute, "clienti")
    op.execute(
        f"CREATE POLICY clienti_citire ON clienti FOR SELECT USING (id = {TENANT} OR {AGENTIE} "
        f"OR id IN (SELECT tenant_id FROM alocari WHERE utilizator_id = {UTILIZATOR}))"
    )
    op.execute(f"CREATE POLICY clienti_inserare ON clienti FOR INSERT WITH CHECK ({AGENTIE})")
    op.execute(f"CREATE POLICY clienti_modificare ON clienti FOR UPDATE USING ({AGENTIE}) WITH CHECK ({AGENTIE})")
    op.execute("GRANT SELECT, INSERT, UPDATE ON clienti TO ama_app")

    # utilizatori: identitate globală (fără tenant_id). Rândul propriu, agenția sau fluxul de autentificare.
    activeaza_rls(op.execute, "utilizatori")
    op.execute(
        f"CREATE POLICY utilizatori_acces ON utilizatori FOR SELECT "
        f"USING (id = {UTILIZATOR} OR {AGENTIE} OR (SELECT ama_auth()))"
    )
    op.execute(f"CREATE POLICY utilizatori_inserare ON utilizatori FOR INSERT WITH CHECK ({AGENTIE})")
    op.execute(
        f"CREATE POLICY utilizatori_modificare ON utilizatori FOR UPDATE "
        f"USING (id = {UTILIZATOR} OR {AGENTIE} OR (SELECT ama_auth())) "
        f"WITH CHECK (id = {UTILIZATOR} OR {AGENTIE} OR (SELECT ama_auth()))"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON utilizatori TO ama_app")

    # apartenente: politica standard pe client + rândurile proprii și fluxul de autentificare la citire.
    activeaza_rls_tenant(op.execute, "apartenente")
    op.execute(
        f"CREATE POLICY apartenente_proprii ON apartenente FOR SELECT USING (utilizator_id = {UTILIZATOR} OR (SELECT ama_auth()))"
    )


def downgrade() -> None:
    op.execute("DROP POLICY clienti_citire ON clienti")  # depinde de alocari
    for tabel in ("apartenente", "alocari", "utilizatori", "clienti"):
        op.execute(f"DROP TABLE {tabel}")
