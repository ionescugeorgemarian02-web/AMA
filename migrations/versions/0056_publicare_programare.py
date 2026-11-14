"""Planificarea publicării prin API (F9.7, D4, docs/15 §15.5)

Revizia: 0056
Anterioara: 0055

- `publicare_reguli`: pe client și canal, sloturile (ora locală, pe zi a săptămânii), plafonul pe zi și pauza
  minimă între postări (frecvența).
- `publicare_zile_blocate`: zilele în care un client nu publică nimic (sărbători, evenimente sensibile,
cereri).
- `publicari_programate`: postarea unei versiuni aprobate, la minutul ales; pleacă prin executorul de efecte.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

CANAL = "CHECK (canal ~ '^[a-z][a-z0-9_]{1,39}$')"


def upgrade() -> None:
    op.execute(
        f"""CREATE TABLE publicare_reguli (
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            canal text NOT NULL {CANAL},
            sloturi jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(sloturi) = 'object'),
            max_pe_zi integer NOT NULL DEFAULT 1 CHECK (max_pe_zi BETWEEN 1 AND 50),
            pauza_minima_min integer NOT NULL DEFAULT 180 CHECK (pauza_minima_min BETWEEN 0 AND 10080),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, canal)
        )"""
    )
    activeaza_rls_tenant(op.execute, "publicare_reguli")
    op.execute(
        """CREATE TABLE publicare_zile_blocate (
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            zi date NOT NULL,
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 300),
            creat_la timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, zi)
        )"""
    )
    activeaza_rls_tenant(op.execute, "publicare_zile_blocate", drepturi="SELECT, INSERT, UPDATE, DELETE")
    op.execute(
        f"""CREATE TABLE publicari_programate (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            versiune integer NOT NULL CHECK (versiune >= 1),
            canal text NOT NULL {CANAL},
            la timestamptz NOT NULL,
            stare text NOT NULL DEFAULT 'programata' CHECK (stare IN ('programata', 'plecata', 'asistata',
            'anulata')), motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 300),
            efect_id uuid,
            creat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (livrabil_id, versiune)
        )"""
    )
    op.execute(
        "CREATE INDEX publicari_programate_scadente ON publicari_programate (la) WHERE stare = 'programata'"
    )
    activeaza_rls_tenant(op.execute, "publicari_programate")


def downgrade() -> None:
    op.execute("DROP TABLE publicari_programate")
    op.execute("DROP TABLE publicare_zile_blocate")
    op.execute("DROP TABLE publicare_reguli")
