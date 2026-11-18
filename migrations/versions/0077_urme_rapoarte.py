"""FT.4: rapoartele lunare ale urmelor (analiza automată), la nivel de agenție

Revizia: 0077
Anterioara: 0076
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE urme_rapoarte (
            id uuid PRIMARY KEY,
            luna date NOT NULL UNIQUE CHECK (extract(day FROM luna) = 1),
            generat_la timestamptz NOT NULL DEFAULT now(),
            continut jsonb NOT NULL
        )"""
    )
    activeaza_rls(op.execute, "urme_rapoarte")
    op.execute(
        "CREATE POLICY urme_rapoarte_agentie ON urme_rapoarte USING ((SELECT ama_agency())) "
        "WITH CHECK ((SELECT ama_agency()))"
    )
    op.execute("REVOKE ALL ON urme_rapoarte FROM ama_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON urme_rapoarte TO ama_app")


def downgrade() -> None:
    op.execute("DROP TABLE urme_rapoarte")
