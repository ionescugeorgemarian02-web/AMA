"""Învățare, prima treaptă: loturile de reflecție și lecțiile de playbook (F11.1, F11.2, docs/11 §11.3)

Revizia: 0090
Anterioara: 0061

- `loturi_reflectie`: un lot închis de postări măsurate ale unui client, peste care a rulat Reflectorul.
- `lectii`: un rând scurt de playbook (11.3): domeniu (client, canal, agent), text, dovezi și cele două
  contoare („a ajutat”, „a dăunat”). `stare`: `propusa` (de Reflector) → `activa` (aprobată) / `respinsa`;
  `retrasa` (automat, când a dăunat mai mult decât a ajutat, sau de om). `sensibila`: atinge conformitatea,
  prețurile sau promisiunile și cere aprobarea proprietarului. `cheie` împiedică aceeași lecție de două ori.
  Datele unui client nu ajung la alt client (11.6, punctul 7): lecțiile sunt pe client, cu izolare pe rând.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0090"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE loturi_reflectie (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            de_la timestamptz NOT NULL,
            pana_la timestamptz NOT NULL,
            postari integer NOT NULL CHECK (postari >= 1),
            propuneri integer NOT NULL DEFAULT 0 CHECK (propuneri >= 0),
            creat_la timestamptz NOT NULL DEFAULT now(),
            CHECK (pana_la > de_la)
        )"""
    )
    activeaza_rls_tenant(op.execute, "loturi_reflectie")
    op.execute(
        """CREATE TABLE lectii (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            lot_id uuid REFERENCES loturi_reflectie (id),
            cheie text NOT NULL CHECK (length(cheie) BETWEEN 3 AND 200),
            domeniu_tip text NOT NULL CHECK (domeniu_tip IN ('client', 'canal', 'agent')),
            domeniu text NOT NULL DEFAULT '' CHECK (length(domeniu) <= 80),
            text text NOT NULL CHECK (length(text) BETWEEN 10 AND 400),
            dovezi jsonb NOT NULL CHECK (jsonb_typeof(dovezi) = 'array' AND jsonb_array_length(dovezi) >= 1),
            sursa text NOT NULL CHECK (sursa IN ('rezultate', 'verdicte', 'decizii')),
            sensibila boolean NOT NULL DEFAULT false,
            stare text NOT NULL DEFAULT 'propusa' CHECK (stare IN ('propusa', 'activa', 'respinsa', 'retrasa')),
            a_ajutat integer NOT NULL DEFAULT 0 CHECK (a_ajutat >= 0),
            a_daunat integer NOT NULL DEFAULT 0 CHECK (a_daunat >= 0),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 300),
            decis_de uuid REFERENCES utilizatori (id),
            decis_la timestamptz,
            creat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT lectii_unic UNIQUE (tenant_id, cheie)
        )"""
    )
    op.execute(
        "CREATE INDEX lectii_active ON lectii (tenant_id, domeniu_tip, domeniu) WHERE stare = 'activa'"
    )
    activeaza_rls_tenant(op.execute, "lectii")


def downgrade() -> None:
    op.execute("DROP TABLE lectii")
    op.execute("DROP TABLE loturi_reflectie")
