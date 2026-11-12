"""Planificatorul de capacitate (F3.11, A4, docs/05, docs/23)

Revizia: 0020
Anterioara: 0019

- `livrabile.nu_inainte_de`: un livrabil `planificat` nu poate trece în `briefat` înainte de acest moment (verificat în
  `productie.muta`). Planificatorul îl pune când amână un livrabil care nu încape în cotele zilei.
- `planificare_costuri`: costul estimat al unui tip de livrabil, ca DATE: apeluri și tokeni pe profil de sarcină, minute de CPU
  pe culoar greu. Valori de pornire, nemăsurate; se editează. Rândul `_implicit` se aplică tipurilor fără rând propriu.
- `planificare_planuri`: planul zilnic (cererea față de capacitate, ce s-a păstrat / amânat, alerta). La nivel de agenție, fără date
  de client (doar numere și identificatori).
- `planificare_decizii`: decizia pe fiecare livrabil, cu `tenant_id` și RLS.
"""

import json

import sqlalchemy as sa
from alembic import op

from app.db.rls import activeaza_rls, activeaza_rls_tenant

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"
CITIRE = (
    "((SELECT ama_agency()) OR (SELECT ama_tenant_id()) IS NOT NULL OR (SELECT ama_user_id()) IS NOT NULL)"
)


def upgrade() -> None:
    op.execute("ALTER TABLE livrabile ADD COLUMN nu_inainte_de timestamptz")
    op.execute(
        "CREATE INDEX livrabile_amanate ON livrabile (nu_inainte_de) WHERE nu_inainte_de IS NOT NULL AND stare = 'planificat'"
    )
    op.execute(
        """CREATE TABLE planificare_costuri (
            tip text PRIMARY KEY CHECK (tip ~ '^_?[a-z][a-z0-9_]{1,39}$'),
            profiluri jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(profiluri) = 'object'),
            minute_cpu numeric(8, 2) NOT NULL DEFAULT 0 CHECK (minute_cpu >= 0),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_de uuid REFERENCES utilizatori (id)
        )"""
    )
    activeaza_rls(op.execute, "planificare_costuri")
    op.execute(f"CREATE POLICY planificare_costuri_citire ON planificare_costuri FOR SELECT USING ({CITIRE})")
    op.execute(
        f"CREATE POLICY planificare_costuri_adaugare ON planificare_costuri FOR INSERT WITH CHECK ({AGENTIE})"
    )
    op.execute(
        f"CREATE POLICY planificare_costuri_schimbare ON planificare_costuri FOR UPDATE USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON planificare_costuri TO ama_app")
    op.execute("GRANT DELETE ON planificare_costuri TO ama_app")
    op.execute(
        f"CREATE POLICY planificare_costuri_stergere ON planificare_costuri FOR DELETE USING ({AGENTIE})"
    )
    _semana()

    op.execute(
        """CREATE TABLE planificare_planuri (
            zi date PRIMARY KEY,
            calculat_la timestamptz NOT NULL DEFAULT now(),
            livrabile integer NOT NULL CHECK (livrabile >= 0),
            pastrate integer NOT NULL CHECK (pastrate >= 0),
            amanate integer NOT NULL CHECK (amanate >= 0),
            protejate_peste_capacitate boolean NOT NULL DEFAULT false,
            cerere jsonb NOT NULL DEFAULT '{}'::jsonb,
            capacitate jsonb NOT NULL DEFAULT '{}'::jsonb,
            alerta text NOT NULL DEFAULT '' CHECK (length(alerta) <= 1000)
        )"""
    )
    activeaza_rls(op.execute, "planificare_planuri")
    op.execute(f"CREATE POLICY planificare_planuri_citire ON planificare_planuri FOR SELECT USING ({CITIRE})")
    op.execute(
        f"CREATE POLICY planificare_planuri_adaugare ON planificare_planuri FOR INSERT WITH CHECK ({AGENTIE})"
    )
    op.execute(
        f"CREATE POLICY planificare_planuri_schimbare ON planificare_planuri FOR UPDATE USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON planificare_planuri TO ama_app")

    op.execute(
        """CREATE TABLE planificare_decizii (
            zi date NOT NULL REFERENCES planificare_planuri (zi),
            livrabil_id uuid NOT NULL,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            tip text NOT NULL,
            decizie text NOT NULL CHECK (decizie IN ('pastrat', 'amanat', 'protejat')),
            prioritate text NOT NULL CHECK (prioritate IN ('P0', 'P1', 'P2', 'P3')),
            termen_la timestamptz,
            nu_inainte_de timestamptz,
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 300),
            creat_la timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (zi, livrabil_id)
        )"""
    )
    op.execute("CREATE INDEX planificare_decizii_client ON planificare_decizii (tenant_id, zi DESC)")
    activeaza_rls_tenant(op.execute, "planificare_decizii", drepturi="SELECT, INSERT, UPDATE")


def _semana() -> None:
    from app.planificare.costuri import COSTURI_IMPLICITE

    conn = op.get_bind()
    conn.execute(sa.text("SELECT set_config('app.agency', '1', true)"))
    for tip, (profiluri, cpu) in COSTURI_IMPLICITE.items():
        conn.execute(
            sa.text(
                "INSERT INTO planificare_costuri (tip, profiluri, minute_cpu) "
                "VALUES (:t, CAST(:p AS jsonb), :c) ON CONFLICT (tip) DO NOTHING"
            ),
            {"t": tip, "p": json.dumps(profiluri), "c": cpu},
        )


def downgrade() -> None:
    op.execute("DROP TABLE planificare_decizii")
    op.execute("DROP TABLE planificare_planuri")
    op.execute("DROP TABLE planificare_costuri")
    op.execute("DROP INDEX livrabile_amanate")
    op.execute("ALTER TABLE livrabile DROP COLUMN nu_inainte_de")
