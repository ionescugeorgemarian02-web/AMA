"""Panoul: abonamente push, livrare, opriri, Telegram

Revizia: 0005
Anterioara: 0004

Toate tabelele de aici sunt la nivel de agenție sau pe utilizator; singura coloană `tenant_id` este cea din
`oprituri` (oprirea pe un client), cu politica ei explicită.
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"
UTILIZATOR = "(SELECT ama_user_id())"
TENANT = "(SELECT ama_tenant_id())"
TABELE = (
    "abonamente_push",
    "cereri_livrare",
    "livrari",
    "oprituri",
    "telegram_actualizari",
    "telegram_confirmari",
)


def _doar_agentie(tabel: str, drepturi: str) -> None:
    activeaza_rls(op.execute, tabel)
    op.execute(f"CREATE POLICY {tabel}_agentie ON {tabel} USING ({AGENTIE}) WITH CHECK ({AGENTIE})")
    op.execute(f"GRANT {drepturi} ON {tabel} TO ama_app")


def upgrade() -> None:
    # --- Web Push (F1.7): fiecare utilizator își atinge doar rândurile; agenția citește și șterge abonamente moarte
    op.execute(
        """CREATE TABLE abonamente_push (
            id uuid PRIMARY KEY,
            utilizator_id uuid NOT NULL REFERENCES utilizatori (id),
            endpoint text NOT NULL UNIQUE CHECK (length(endpoint) <= 2000 AND endpoint LIKE 'https://%'),
            p256dh text NOT NULL CHECK (length(p256dh) <= 200),
            auth text NOT NULL CHECK (length(auth) <= 100),
            user_agent text,
            creat_la timestamptz NOT NULL DEFAULT now(),
            ultima_trimitere timestamptz
        )"""
    )
    op.execute("CREATE INDEX abonamente_push_utilizator ON abonamente_push (utilizator_id)")
    activeaza_rls(op.execute, "abonamente_push")
    op.execute(
        f"CREATE POLICY abonamente_citire ON abonamente_push FOR SELECT USING (utilizator_id = {UTILIZATOR} OR {AGENTIE})"
    )
    op.execute(
        f"CREATE POLICY abonamente_adaugare ON abonamente_push FOR INSERT WITH CHECK (utilizator_id = {UTILIZATOR})"
    )
    op.execute(
        f"CREATE POLICY abonamente_schimbare ON abonamente_push FOR UPDATE USING (utilizator_id = {UTILIZATOR}) "
        f"WITH CHECK (utilizator_id = {UTILIZATOR})"
    )
    op.execute(
        f"CREATE POLICY abonamente_stergere ON abonamente_push FOR DELETE USING (utilizator_id = {UTILIZATOR} OR {AGENTIE})"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON abonamente_push TO ama_app")

    # --- Livrare (F1.8)
    op.execute(
        """CREATE TABLE cereri_livrare (
            id uuid PRIMARY KEY,
            tip text NOT NULL CHECK (tip IN ('promovare', 'revenire')),
            imagine text CHECK (imagine ~ '^[a-z0-9][a-z0-9._/:-]*@sha256:[0-9a-f]{64}$'),
            versiune text,
            stare text NOT NULL DEFAULT 'solicitata'
                CHECK (stare IN ('solicitata', 'in_curs', 'reusita', 'esuata', 'revenita')),
            solicitat_de uuid REFERENCES utilizatori (id),
            detalii text NOT NULL DEFAULT '',
            creat_la timestamptz NOT NULL DEFAULT clock_timestamp(),
            actualizat_la timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK ((tip = 'promovare') = (imagine IS NOT NULL))
        )"""
    )
    op.execute("CREATE INDEX cereri_livrare_stare ON cereri_livrare (stare, creat_la)")
    _doar_agentie("cereri_livrare", "SELECT, INSERT, UPDATE")
    op.execute(
        """CREATE TABLE livrari (
            id uuid PRIMARY KEY,
            mediu text NOT NULL CHECK (mediu IN ('staging', 'productie')),
            cheie text NOT NULL,
            cerere_id uuid,
            imagine text CHECK (imagine ~ '^[a-z0-9][a-z0-9._/:-]*@sha256:[0-9a-f]{64}$'),
            versiune text,
            stare text NOT NULL CHECK (stare IN ('in_curs', 'reusita', 'esuata', 'revenita')),
            detalii text NOT NULL DEFAULT '',
            verificari jsonb NOT NULL DEFAULT '[]'::jsonb,
            momentul timestamptz NOT NULL,
            creat_la timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE (mediu, cheie, stare)
        )"""
    )
    op.execute("CREATE INDEX livrari_mediu ON livrari (mediu, creat_la DESC)")
    _doar_agentie("livrari", "SELECT, INSERT")

    # --- Opriri (F1.10, 7.8). `tenant_id` doar pentru oprirea pe client; rândurile globale se văd de toți.
    op.execute(
        """CREATE TABLE oprituri (
            id uuid PRIMARY KEY,
            tip text NOT NULL CHECK (tip IN ('publicare', 'reclame', 'invatare', 'apeluri_platite', 'client')),
            tenant_id uuid REFERENCES clienti (id),
            activ boolean NOT NULL DEFAULT false,
            motiv text NOT NULL DEFAULT '',
            canal text NOT NULL CHECK (canal IN ('panou', 'telegram')),
            schimbat_de uuid REFERENCES utilizatori (id),
            schimbat_la timestamptz NOT NULL DEFAULT now(),
            CHECK ((tip = 'client') = (tenant_id IS NOT NULL))
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX oprituri_unic ON oprituri (tip, COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid))"
    )
    activeaza_rls(op.execute, "oprituri")
    op.execute(
        f"CREATE POLICY oprituri_citire ON oprituri FOR SELECT "
        f"USING (tenant_id IS NULL OR tenant_id = {TENANT} OR {AGENTIE})"
    )
    op.execute(f"CREATE POLICY oprituri_adaugare ON oprituri FOR INSERT WITH CHECK ({AGENTIE})")
    op.execute(
        f"CREATE POLICY oprituri_schimbare ON oprituri FOR UPDATE USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON oprituri TO ama_app")

    # --- Telegram (F1.10)
    op.execute(
        """CREATE TABLE telegram_actualizari (
            update_id bigint PRIMARY KEY,
            primit_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    _doar_agentie("telegram_actualizari", "SELECT, INSERT, DELETE")
    op.execute(
        """CREATE TABLE telegram_confirmari (
            chat_id bigint PRIMARY KEY,
            cod_hash bytea NOT NULL CHECK (length(cod_hash) = 32),
            tip text NOT NULL,
            tenant_id uuid REFERENCES clienti (id),
            expira_la timestamptz NOT NULL
        )"""
    )
    _doar_agentie("telegram_confirmari", "SELECT, INSERT, UPDATE, DELETE")


def downgrade() -> None:
    for t in reversed(TABELE):
        op.execute(f"DROP TABLE {t}")
