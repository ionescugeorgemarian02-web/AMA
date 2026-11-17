"""Reclame: conturile de reclame și rezultatele citite (F13.1, docs/16 §16.1–16.4, docs/20 „Reclame”)

Revizia: 0070
Anterioara: 0095

- `reclame_conturi`: contul de reclame al unui client (sau al agenției) la o platformă, cu plafoanele din
  contract (zilnic, lunar, pe campanie) și regulile gardianului de buget (16.4), editabile pe client.
- `reclame_rezultate`: cifrele zilnice ale campaniilor și reclamelor, cum le arată managerul de reclame.
  Se rescriu la fiecare citire (platforma corectează zilele recente după atribuire).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0070"
down_revision = "0095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE reclame_conturi (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            platforma text NOT NULL CHECK (platforma IN ('meta', 'google')),
            cont_extern text NOT NULL CHECK (cont_extern ~ '^[A-Za-z0-9_-]{1,40}$'),
            nume text NOT NULL CHECK (length(nume) BETWEEN 2 AND 120),
            moneda text NOT NULL DEFAULT 'RON' CHECK (moneda ~ '^[A-Z]{3}$'),
            al_agentiei boolean NOT NULL DEFAULT false,
            activ boolean NOT NULL DEFAULT true,
            plafon_zilnic_bani bigint NOT NULL CHECK (plafon_zilnic_bani > 0),
            plafon_lunar_bani bigint NOT NULL,
            plafon_campanie_bani bigint NOT NULL CHECK (plafon_campanie_bani > 0),
            schimbare_max_pct integer NOT NULL DEFAULT 20 CHECK (schimbare_max_pct BETWEEN 1 AND 100),
            asteptare_ore integer NOT NULL DEFAULT 48 CHECK (asteptare_ore BETWEEN 0 AND 720),
            schimbari_pe_zi integer NOT NULL DEFAULT 5 CHECK (schimbari_pe_zi BETWEEN 1 AND 50),
            citit_la timestamptz,
            eroare_citire text CHECK (length(eroare_citire) <= 300),
            creat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (platforma, cont_extern),
            CHECK (plafon_lunar_bani >= plafon_zilnic_bani),
            CHECK (plafon_campanie_bani <= plafon_zilnic_bani)
        )"""
    )
    activeaza_rls_tenant(op.execute, "reclame_conturi")
    op.execute(
        """CREATE TABLE reclame_rezultate (
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            cont_id uuid NOT NULL REFERENCES reclame_conturi (id),
            nivel text NOT NULL CHECK (nivel IN ('campanie', 'reclama')),
            obiect_extern text NOT NULL CHECK (length(obiect_extern) BETWEEN 1 AND 60),
            nume text NOT NULL DEFAULT '' CHECK (length(nume) <= 300),
            parinte_extern text NOT NULL DEFAULT '',
            zi date NOT NULL,
            cheltuiala_bani bigint NOT NULL CHECK (cheltuiala_bani >= 0),
            afisari bigint NOT NULL CHECK (afisari >= 0),
            clicuri bigint NOT NULL CHECK (clicuri >= 0),
            rezultate integer NOT NULL CHECK (rezultate >= 0),
            citit_la timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (cont_id, nivel, obiect_extern, zi)
        )"""
    )
    op.execute("CREATE INDEX reclame_rezultate_zi ON reclame_rezultate (cont_id, zi)")
    activeaza_rls_tenant(op.execute, "reclame_rezultate")


def downgrade() -> None:
    op.execute("DROP TABLE reclame_rezultate")
    op.execute("DROP TABLE reclame_conturi")
