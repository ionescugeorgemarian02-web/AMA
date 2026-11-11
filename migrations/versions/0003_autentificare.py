"""Autentificare: al doilea factor, sesiuni, încercări de autentificare, coduri de recuperare

Revizia: 0003
Anterioara: 0002
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

AUTH = "(SELECT ama_auth())"
AGENTIE = "(SELECT ama_agency())"
UTILIZATOR = "(SELECT ama_user_id())"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE utilizatori ADD COLUMN totp_secret_enc bytea"
    )  # criptat (AES-GCM), niciodată în clar
    op.execute("ALTER TABLE utilizatori ADD COLUMN totp_activ boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE utilizatori ADD COLUMN totp_ultim_pas bigint")  # protecție la reluarea codului

    op.execute(
        """CREATE TABLE sesiuni (
            id uuid PRIMARY KEY,
            token_hash bytea NOT NULL UNIQUE CHECK (length(token_hash) = 32),
            utilizator_id uuid NOT NULL REFERENCES utilizatori (id),
            tenant_activ_id uuid REFERENCES clienti (id),
            mfa_verificat boolean NOT NULL,
            csrf_token text NOT NULL,
            creat_la timestamptz NOT NULL DEFAULT now(),
            ultima_activitate timestamptz NOT NULL DEFAULT now(),
            expira_absolut timestamptz NOT NULL,
            revocata_la timestamptz,
            ip text,
            user_agent text
        )"""
    )
    op.execute("CREATE INDEX sesiuni_utilizator ON sesiuni (utilizator_id)")
    activeaza_rls(op.execute, "sesiuni")
    conditie = f"({AUTH} OR {AGENTIE} OR utilizator_id = {UTILIZATOR})"
    op.execute(f"CREATE POLICY sesiuni_acces ON sesiuni USING {conditie} WITH CHECK {conditie}")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON sesiuni TO ama_app")

    op.execute(
        """CREATE TABLE incercari_autentificare (
            id uuid PRIMARY KEY,
            creat_la timestamptz NOT NULL DEFAULT now(),
            cheie_cont bytea NOT NULL,
            ip text NOT NULL,
            tip text NOT NULL CHECK (tip IN ('parola', 'totp', 'recuperare')),
            reusit boolean NOT NULL
        )"""
    )
    op.execute("CREATE INDEX incercari_cont ON incercari_autentificare (cheie_cont, creat_la DESC)")
    op.execute("CREATE INDEX incercari_ip ON incercari_autentificare (ip, creat_la DESC)")
    activeaza_rls(op.execute, "incercari_autentificare")
    op.execute(
        f"CREATE POLICY incercari_doar_autentificare ON incercari_autentificare USING ({AUTH}) WITH CHECK ({AUTH})"
    )
    op.execute("GRANT SELECT, INSERT, DELETE ON incercari_autentificare TO ama_app")

    op.execute(
        """CREATE TABLE coduri_recuperare (
            id uuid PRIMARY KEY,
            utilizator_id uuid NOT NULL REFERENCES utilizatori (id),
            cod_hash bytea NOT NULL,
            creat_la timestamptz NOT NULL DEFAULT now(),
            folosit_la timestamptz,
            UNIQUE (utilizator_id, cod_hash)
        )"""
    )
    activeaza_rls(op.execute, "coduri_recuperare")
    conditie = f"({AUTH} OR utilizator_id = {UTILIZATOR})"
    op.execute(f"CREATE POLICY coduri_acces ON coduri_recuperare USING {conditie} WITH CHECK {conditie}")
    op.execute("GRANT SELECT, INSERT, UPDATE ON coduri_recuperare TO ama_app")


def downgrade() -> None:
    for tabel in ("coduri_recuperare", "incercari_autentificare", "sesiuni"):
        op.execute(f"DROP TABLE {tabel}")
    for coloana in ("totp_ultim_pas", "totp_activ", "totp_secret_enc"):
        op.execute(f"ALTER TABLE utilizatori DROP COLUMN {coloana}")
