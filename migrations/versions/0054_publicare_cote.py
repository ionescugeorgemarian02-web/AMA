"""Publicarea prin API: contorul de unități pe platformă și zi (F9.4, docs/15 §15.1, docs/02)

Revizia: 0054
Anterioara: 0053

- `publicare_cote`: unitățile consumate pe zi (YouTube: ziua Pacific, 10.000 pe zi [I]). Date de agenție
(cota e a
  proiectului, nu a clientului): oricine autentificat citește, agenția scrie (ca `gateway_contoare`).
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"
CITIRE = (
    "((SELECT ama_agency()) OR (SELECT ama_tenant_id()) IS NOT NULL OR (SELECT ama_user_id()) IS NOT NULL)"
)


def upgrade() -> None:
    op.execute(
        """CREATE TABLE publicare_cote (
            platforma text NOT NULL CHECK (platforma ~ '^[a-z][a-z0-9_]{1,30}$'),
            zi date NOT NULL,
            unitati integer NOT NULL DEFAULT 0 CHECK (unitati >= 0),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (platforma, zi)
        )"""
    )
    activeaza_rls(op.execute, "publicare_cote")
    op.execute(f"CREATE POLICY publicare_cote_citire ON publicare_cote FOR SELECT USING ({CITIRE})")
    op.execute(f"CREATE POLICY publicare_cote_adaugare ON publicare_cote FOR INSERT WITH CHECK ({AGENTIE})")
    op.execute(
        f"CREATE POLICY publicare_cote_schimbare ON publicare_cote FOR UPDATE USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON publicare_cote TO ama_app")


def downgrade() -> None:
    op.execute("DROP TABLE publicare_cote")
