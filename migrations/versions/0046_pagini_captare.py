"""Paginile de captare găzduite de platformă (F7.9, D2 + E3, docs/04, docs/19 §19.1)

Revizia: 0046
Anterioara: 0045

- `pagini_captare`: propunerea arhitectului de ofertă (magnet, traseu), textele copywriterului (pagina, 3 reclame,
  studiul de caz), verdictul validării (G2, G3, G9 + un singur apel la acțiune) și publicarea de către un om.
  Pagina publicată se servește la `/site/p/<slug>`; o publicare nouă pe același slug o înlocuiește pe cea veche.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE pagini_captare (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            slug text NOT NULL CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND length(slug) <= 80),
            tinta text NOT NULL CHECK (tinta ~ '^/' AND length(tinta) <= 200),
            propunere jsonb NOT NULL,
            continut jsonb NOT NULL,
            validare jsonb NOT NULL,
            stare text NOT NULL DEFAULT 'propus' CHECK (stare IN ('propus', 'validat', 'respins', 'publicat', 'inlocuit')),
            publicat_de uuid REFERENCES utilizatori (id),
            publicat_la timestamptz,
            creat_la timestamptz NOT NULL DEFAULT now(),
            CHECK (stare <> 'publicat' OR (publicat_de IS NOT NULL AND publicat_la IS NOT NULL))
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX pagini_captare_publicata ON pagini_captare (slug) WHERE stare = 'publicat'"
    )
    activeaza_rls_tenant(op.execute, "pagini_captare")


def downgrade() -> None:
    op.execute("DROP TABLE pagini_captare")
