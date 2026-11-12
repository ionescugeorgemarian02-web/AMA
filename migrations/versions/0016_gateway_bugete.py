"""Gateway de modele: bugetele pe client și consumul lor (F3.8, docs/08 §8.5)

Revizia: 0016
Anterioara: 0015

- `gateway_bugete_implicite`: UN rând (la nivel de agenție) cu bugetele de pornire: apeluri, tokeni și preț-umbră pe zi și pe
  lună, pragul de avertizare și plafonul garantat al lui P1. Valorile sunt de pornire, nemăsurate; se editează din panou.
- `gateway_bugete_client`: suprascrieri per client (o coloană `NULL` = se aplică valoarea implicită). Cu `tenant_id` și RLS.
- `gateway_consum_client`: contoarele de consum, câte un rând pe (client, fereastră, început de fereastră). Se actualizează
  prin instrucțiuni atomice sub plafon (vezi `app/gateway/bugete.py`), deci corect la concurență; `avertizat` face ca
  notificarea de prag să plece o singură dată pe fereastră. Cu `tenant_id` și RLS.
"""

import sqlalchemy as sa
from alembic import op

from app.db.rls import activeaza_rls, activeaza_rls_tenant

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"
CITIRE = (
    "((SELECT ama_agency()) OR (SELECT ama_tenant_id()) IS NOT NULL OR (SELECT ama_user_id()) IS NOT NULL)"
)


def upgrade() -> None:
    op.execute(
        """CREATE TABLE gateway_bugete_implicite (
            id smallint PRIMARY KEY CHECK (id = 1),
            apeluri_zi integer CHECK (apeluri_zi >= 0),
            tokeni_zi bigint CHECK (tokeni_zi >= 0),
            pret_umbra_zi numeric(14, 4) CHECK (pret_umbra_zi >= 0),
            apeluri_luna integer CHECK (apeluri_luna >= 0),
            tokeni_luna bigint CHECK (tokeni_luna >= 0),
            pret_umbra_luna numeric(14, 4) CHECK (pret_umbra_luna >= 0),
            prag_avertizare numeric(3, 2) NOT NULL DEFAULT 0.80 CHECK (prag_avertizare BETWEEN 0.50 AND 1.00),
            plafon_p1 numeric(4, 2) NOT NULL DEFAULT 1.50 CHECK (plafon_p1 BETWEEN 1.00 AND 10.00),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_de uuid REFERENCES utilizatori (id)
        )"""
    )
    activeaza_rls(op.execute, "gateway_bugete_implicite")
    op.execute(
        f"CREATE POLICY gateway_bugete_implicite_citire ON gateway_bugete_implicite FOR SELECT USING ({CITIRE})"
    )
    op.execute(
        f"CREATE POLICY gateway_bugete_implicite_adaugare ON gateway_bugete_implicite FOR INSERT WITH CHECK ({AGENTIE})"
    )
    op.execute(
        "CREATE POLICY gateway_bugete_implicite_schimbare ON gateway_bugete_implicite FOR UPDATE "
        f"USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON gateway_bugete_implicite TO ama_app")
    # Sămânța (RLS e forțat și pentru proprietar). Valori de pornire, NEMĂSURATE.
    op.get_bind().execute(sa.text("SELECT set_config('app.agency', '1', true)"))
    op.execute(
        """INSERT INTO gateway_bugete_implicite
               (id, apeluri_zi, tokeni_zi, pret_umbra_zi, apeluri_luna, tokeni_luna, pret_umbra_luna)
           VALUES (1, 400, 1500000, 1.50, 8000, 30000000, 30.00)"""
    )

    op.execute(
        """CREATE TABLE gateway_bugete_client (
            tenant_id uuid PRIMARY KEY REFERENCES clienti (id),
            apeluri_zi integer CHECK (apeluri_zi >= 0),
            tokeni_zi bigint CHECK (tokeni_zi >= 0),
            pret_umbra_zi numeric(14, 4) CHECK (pret_umbra_zi >= 0),
            apeluri_luna integer CHECK (apeluri_luna >= 0),
            tokeni_luna bigint CHECK (tokeni_luna >= 0),
            pret_umbra_luna numeric(14, 4) CHECK (pret_umbra_luna >= 0),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_de uuid REFERENCES utilizatori (id)
        )"""
    )
    activeaza_rls_tenant(op.execute, "gateway_bugete_client", drepturi="SELECT, INSERT, UPDATE, DELETE")

    op.execute(
        """CREATE TABLE gateway_consum_client (
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            fereastra text NOT NULL CHECK (fereastra IN ('zi', 'luna')),
            inceput timestamptz NOT NULL,
            apeluri integer NOT NULL DEFAULT 0 CHECK (apeluri >= 0),
            tokeni bigint NOT NULL DEFAULT 0 CHECK (tokeni >= 0),
            pret_umbra numeric(14, 6) NOT NULL DEFAULT 0 CHECK (pret_umbra >= 0),
            avertizat boolean NOT NULL DEFAULT false,
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, fereastra, inceput)
        )"""
    )
    op.execute("CREATE INDEX gateway_consum_client_vechime ON gateway_consum_client (inceput)")
    activeaza_rls_tenant(op.execute, "gateway_consum_client", drepturi="SELECT, INSERT, UPDATE, DELETE")


def downgrade() -> None:
    op.execute("DROP TABLE gateway_consum_client")
    op.execute("DROP TABLE gateway_bugete_client")
    op.execute("DROP TABLE gateway_bugete_implicite")
