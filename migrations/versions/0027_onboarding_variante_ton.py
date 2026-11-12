"""Onboarding: variantele de ton ale ghidului de brand (F4.5, docs/13 §13.8)

Revizia: 0027
Anterioara: 0026

- `onboarding_variante_ton`: cele trei variante de ton propuse dintr-o rulare (`grup_id`), cu promptul și modelul care
  le-au produs și versiunea brieful din care au pornit. Conținutul unei variante nu se schimbă; se marchează doar
  `ales` (cea aleasă, sau cele din care s-a combinat ghidul). Ghidul aprobat este o intrare din Creier
  (`profil_brand`), nu acest tabel.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE onboarding_variante_ton (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            grup_id uuid NOT NULL,
            nr integer NOT NULL CHECK (nr BETWEEN 1 AND 9),
            continut jsonb NOT NULL CHECK (jsonb_typeof(continut) = 'object'),
            prompt text NOT NULL CHECK (length(prompt) BETWEEN 3 AND 100),
            model text,
            brief_versiune integer,
            ales boolean NOT NULL DEFAULT false,
            ales_de uuid REFERENCES utilizatori (id),
            ales_la timestamptz,
            creat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (grup_id, nr)
        )"""
    )
    op.execute(
        "CREATE INDEX onboarding_variante_ton_client ON onboarding_variante_ton (tenant_id, creat_la DESC)"
    )
    activeaza_rls_tenant(op.execute, "onboarding_variante_ton", drepturi="SELECT, INSERT, UPDATE")


def downgrade() -> None:
    op.execute("DROP TABLE onboarding_variante_ton")
