"""Motorul (F2.7): semnalele de viață ale workerilor, evenimentele lor și coada de erori

Revizia: 0006
Anterioara: 0005

Schema bibliotecii de workflow-uri (`dbos`) NU se creează aici: o creează `python -m app.operare.motor.migrare`
(vezi docs/specs/F2.1.md). Tabelele de mai jos sunt ale aplicației:

- `worker_semnale`, `worker_evenimente`: nivel de agenție (fără date de client).
- `coada_erori`: poate purta `tenant_id` (jobul unui client), deci are izolare pe client; `ama_app` nu primește
  DELETE (nimic nu se șterge din coada de erori fără o decizie înregistrată, 22.5).
"""

from alembic import op

from app.db.rls import activeaza_rls, activeaza_rls_tenant

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"
TABELE = ("coada_erori", "worker_evenimente", "worker_semnale")


def upgrade() -> None:
    # --- semnalele de viață (22.3): un rând pe worker, actualizat la fiecare bătaie
    op.execute(
        """CREATE TABLE worker_semnale (
            worker_id text PRIMARY KEY CHECK (length(worker_id) BETWEEN 1 AND 63),
            pid integer NOT NULL,
            versiune text NOT NULL DEFAULT '',
            pornit_la timestamptz NOT NULL DEFAULT now(),
            ultimul_semnal timestamptz NOT NULL DEFAULT now(),
            oprit_curat boolean NOT NULL DEFAULT false,
            oprit_la timestamptz,
            semnalat_mort boolean NOT NULL DEFAULT false
        )"""
    )
    activeaza_rls(op.execute, "worker_semnale")
    op.execute(
        f"CREATE POLICY worker_semnale_agentie ON worker_semnale USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON worker_semnale TO ama_app")

    # --- evenimentele workerilor: doar adăugări (pornit, oprit curat, repornit după cădere, alertă)
    op.execute(
        """CREATE TABLE worker_evenimente (
            id uuid PRIMARY KEY,
            worker_id text NOT NULL,
            tip text NOT NULL CHECK (tip IN
                ('pornit', 'oprit_curat', 'repornit_dupa_cadere', 'fara_semn_de_viata', 'alerta_reporniri')),
            la timestamptz NOT NULL DEFAULT now(),
            detalii jsonb NOT NULL DEFAULT '{}'::jsonb
        )"""
    )
    op.execute("CREATE INDEX worker_evenimente_worker ON worker_evenimente (worker_id, tip, la DESC)")
    activeaza_rls(op.execute, "worker_evenimente")
    op.execute(
        f"CREATE POLICY worker_evenimente_agentie ON worker_evenimente USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute("GRANT SELECT, INSERT ON worker_evenimente TO ama_app")

    # --- coada de erori (22.5): contextul complet al unui job care a eșuat, grupat pe cauză
    op.execute(
        """CREATE TABLE coada_erori (
            id uuid PRIMARY KEY,
            tenant_id uuid REFERENCES clienti (id),
            workflow_id text NOT NULL UNIQUE,
            flux text NOT NULL,
            pas text,
            stare_job text NOT NULL,
            coada text,
            executor_id text,
            eroare_tip text NOT NULL,
            eroare_mesaj text NOT NULL DEFAULT '' CHECK (length(eroare_mesaj) <= 500),
            cauza text NOT NULL CHECK (cauza ~ '^[0-9a-f]{16}$'),
            severitate text NOT NULL CHECK (severitate IN ('critic', 'major', 'minor', 'informativ')),
            stare text NOT NULL DEFAULT 'noua' CHECK (stare IN ('noua', 'reluata', 'inchisa')),
            reluari integer NOT NULL DEFAULT 0,
            reluat_ca text,
            context jsonb NOT NULL DEFAULT '{}'::jsonb,
            creat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            inchis_la timestamptz,
            inchis_de uuid REFERENCES utilizatori (id),
            motiv_inchidere text,
            CHECK ((stare = 'inchisa') = (inchis_la IS NOT NULL))
        )"""
    )
    op.execute("CREATE INDEX coada_erori_deschise ON coada_erori (stare, severitate, creat_la DESC)")
    op.execute("CREATE INDEX coada_erori_cauza ON coada_erori (cauza, stare)")
    op.execute("CREATE INDEX coada_erori_client ON coada_erori (tenant_id) WHERE tenant_id IS NOT NULL")
    # fără DELETE: aplicația nu poate șterge nimic din coada de erori
    activeaza_rls_tenant(op.execute, "coada_erori", drepturi="SELECT, INSERT, UPDATE")


def downgrade() -> None:
    for t in TABELE:
        op.execute(f"DROP TABLE {t}")
