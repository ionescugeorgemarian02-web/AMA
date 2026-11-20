"""Etapa de idee a livrabilelor (F-idee, D-032): conceptele propuse, notele criticului, validarea și alegerea.

`idei_concepte`: un rând pe concept (runda 1 = propunerea autorului plus varianta îmbunătățită a criticului,
runda 2 = rescrierea cu obiecțiile), cu notele pe criterii, obiecțiile, problemele deterministe și alegerea
(cel mult un concept `ales` pe livrabil; fără ales, ideea așteaptă omul).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0143"
down_revision = "0142"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE idei_concepte (
        id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES clienti(id),
        livrabil_id uuid NOT NULL REFERENCES livrabile(id),
        runda integer NOT NULL CHECK (runda IN (1, 2)), nr integer NOT NULL CHECK (nr >= 1),
        sursa text NOT NULL CHECK (sursa IN ('propus', 'imbunatatit', 'rescris')),
        concept jsonb NOT NULL, note jsonb NOT NULL DEFAULT '{}', scor integer,
        obiectii jsonb NOT NULL DEFAULT '[]', probleme jsonb NOT NULL DEFAULT '[]',
        ales boolean NOT NULL DEFAULT false, motiv text NOT NULL DEFAULT '',
        model_autor text, model_critic text, autoevaluare boolean NOT NULL DEFAULT false,
        decis_de uuid, creat_la timestamptz NOT NULL DEFAULT now(),
        UNIQUE (tenant_id, livrabil_id, runda, sursa, nr))""")
    op.execute("CREATE UNIQUE INDEX idei_concepte_ales ON idei_concepte(livrabil_id) WHERE ales")
    activeaza_rls_tenant(op.execute, "idei_concepte")


def downgrade() -> None:
    op.execute("DROP TABLE idei_concepte")
