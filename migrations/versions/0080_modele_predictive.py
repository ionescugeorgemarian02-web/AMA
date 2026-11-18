"""Învățare: modelele predictive, doar peste pragul de date (F14.3, F14.5, docs/11 §11.2 N6)

Revizia: 0080
Anterioara: 0079

- `modele_predictive`: o încercare de antrenare pe un tip (`performanta` pe client și canal; `lead` și `plecare`
  la nivel de agenție, cu `tenant_id` gol), cu numărul de exemple și pragul. Sub prag nu se antrenează nimic
  (`sub_prag`). Peste prag: metricile pe date trecute (AUC pe testul din urmă, față de alegerea la întâmplare sau
  de regula simplă, cu intervalul bootstrap) și `valid` doar dacă modelul bate referința cu marja cerută.
  Rândurile unui client le vede doar clientul (RLS); cele de agenție, doar agenția (Constituția, punctul 7).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE modele_predictive (
            id uuid PRIMARY KEY,
            tenant_id uuid REFERENCES clienti (id),
            tip text NOT NULL CHECK (tip IN ('performanta', 'lead', 'plecare')),
            canal text NOT NULL DEFAULT '' CHECK (length(canal) <= 40),
            n_exemple integer NOT NULL CHECK (n_exemple >= 0),
            prag integer NOT NULL CHECK (prag >= 1),
            stare text NOT NULL CHECK (stare IN ('sub_prag', 'nu_bate', 'valid')),
            referinta text NOT NULL CHECK (referinta IN ('intamplare', 'reguli')),
            metrici jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metrici) = 'object'),
            model jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(model) = 'object'),
            antrenat_la timestamptz NOT NULL DEFAULT now(),
            CHECK ((tip = 'performanta') = (tenant_id IS NOT NULL)),
            CHECK (stare = 'sub_prag' OR n_exemple >= prag)
        )"""
    )
    op.execute(
        "CREATE INDEX modele_predictive_ultimul ON modele_predictive (tip, tenant_id, canal, antrenat_la DESC)"
    )
    activeaza_rls_tenant(op.execute, "modele_predictive")


def downgrade() -> None:
    op.execute("DROP TABLE modele_predictive")
