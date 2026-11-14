"""Site-ul public: analiza de trafic proprie și articolele blogului (F7.1, docs/19 §19.1)

Revizia: 0039
Anterioara: 0038

- `site_vizite`: numărul de vizite pe zi și pe pagină, DOAR cu acordul pentru cookie-uri de analiză; fără IP, fără
  identificatori, fără cookie de urmărire (analiză proprie, găzduită local).
- `site_articole`: articolele publicate pe blog (scrise de platformă din F7.10), cu sursele citate.
Ambele sunt date ale agenției (nu ale unui client): le citește și le scrie doar contextul de agenție.
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"


def politici_agentie(tabel: str, drepturi: str = "SELECT, INSERT, UPDATE") -> None:
    activeaza_rls(op.execute, tabel)
    op.execute(f"CREATE POLICY {tabel}_agentie ON {tabel} USING ({AGENTIE}) WITH CHECK ({AGENTIE})")
    op.execute(f"GRANT {drepturi} ON {tabel} TO ama_app")


def upgrade() -> None:
    op.execute(
        """CREATE TABLE site_vizite (
            zi date NOT NULL,
            cale text NOT NULL CHECK (cale ~ '^/[a-z0-9/_-]{0,120}$'),
            numar integer NOT NULL DEFAULT 0 CHECK (numar >= 0),
            PRIMARY KEY (zi, cale)
        )"""
    )
    politici_agentie("site_vizite")
    op.execute(
        """CREATE TABLE site_articole (
            id uuid PRIMARY KEY,
            slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND length(slug) <= 90),
            titlu text NOT NULL CHECK (length(titlu) BETWEEN 5 AND 120),
            descriere text NOT NULL CHECK (length(descriere) BETWEEN 20 AND 200),
            cuvant_cheie text NOT NULL DEFAULT '',
            corp jsonb NOT NULL,
            surse jsonb NOT NULL DEFAULT '[]'::jsonb,
            dezvaluire_ai boolean NOT NULL DEFAULT true,
            publicat_la timestamptz,
            creat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    politici_agentie("site_articole")


def downgrade() -> None:
    op.execute("DROP TABLE site_articole")
    op.execute("DROP TABLE site_vizite")
