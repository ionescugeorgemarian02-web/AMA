"""Învățare, a doua treaptă: rulările optimizatorului de prompturi (F14.1, docs/11 §11.5, N5)

Revizia: 0078
Anterioara: 0077

- `optimizari`: o rulare pe o componentă (numele promptului din registrul gateway-ului): versiunea campionului,
  versiunea candidatului (o ciornă nouă în `gateway_prompturi`), scorurile compuse pe antrenare și pe test,
  conformitatea, marja cerută și raportul (ce s-a schimbat și de ce). La nivel de agenție (D-020): setul de aur
  e al agenției, fără date de client; rândul nu are `tenant_id`, doar scopul de agenție îl vede.
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE optimizari (
            id uuid PRIMARY KEY,
            componenta text NOT NULL CHECK (length(componenta) BETWEEN 1 AND 100),
            campion_versiune integer NOT NULL CHECK (campion_versiune >= 1),
            candidat_versiune integer CHECK (candidat_versiune >= 1),
            stare text NOT NULL DEFAULT 'in_curs'
                CHECK (stare IN ('in_curs', 'candidat', 'fara_candidat', 'esuata')),
            scor_campion real CHECK (scor_campion BETWEEN 0 AND 1),
            scor_candidat real CHECK (scor_candidat BETWEEN 0 AND 1),
            marja real NOT NULL CHECK (marja >= 0 AND marja <= 1),
            raport jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(raport) = 'object'),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 300),
            inceput_la timestamptz NOT NULL DEFAULT now(),
            incheiat_la timestamptz,
            CHECK ((stare = 'candidat') = (candidat_versiune IS NOT NULL)),
            CHECK ((stare = 'in_curs') = (incheiat_la IS NULL))
        )"""
    )
    op.execute("CREATE INDEX optimizari_componenta ON optimizari (componenta, inceput_la DESC)")
    activeaza_rls(op.execute, "optimizari")
    op.execute(
        "CREATE POLICY optimizari_agentie ON optimizari USING ((SELECT ama_agency())) "
        "WITH CHECK ((SELECT ama_agency()))"
    )
    op.execute("REVOKE ALL ON optimizari FROM ama_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON optimizari TO ama_app")


def downgrade() -> None:
    op.execute("DROP TABLE optimizari")
