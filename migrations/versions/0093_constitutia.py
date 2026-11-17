"""Învățare: Constituția, gardurile tehnice (F11.5, docs/11 §11.6)

Revizia: 0093
Anterioara: 0092

- Declanșatorul `ama_fara_invatare`: orice scriere în regulile validatorilor pe client (`reguli_client`) și în
  registrul de fapte al Creierului (`creier_intrari`, `creier_versiuni`) este refuzată cât tranzacția rulează
  în fluxul de învățare (`app.flux = 'invatare'`). Punctul 1 din 11.6: validatorii sunt în afara învățării.
- `invatare_stare`: starea globală a învățării (un singur rând): butonul de înghețare (punctul 9). Date de
  agenție: oricine autentificat citește, agenția scrie.
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None

PROTEJATE = ("reguli_client", "creier_intrari", "creier_versiuni")
AGENTIE = "(SELECT ama_agency())"
CITIRE = (
    "((SELECT ama_agency()) OR (SELECT ama_tenant_id()) IS NOT NULL OR (SELECT ama_user_id()) IS NOT NULL)"
)


def upgrade() -> None:
    op.execute(
        """CREATE FUNCTION ama_fara_invatare() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF current_setting('app.flux', true) = 'invatare' THEN
                RAISE EXCEPTION 'Constituția: fluxul de învățare nu poate scrie în %', TG_TABLE_NAME
                    USING ERRCODE = '42501';
            END IF;
            RETURN COALESCE(NEW, OLD);
        END $$"""
    )
    for t in PROTEJATE:
        op.execute(
            f"CREATE TRIGGER {t}_fara_invatare BEFORE INSERT OR UPDATE OR DELETE ON {t} "
            "FOR EACH ROW EXECUTE FUNCTION ama_fara_invatare()"
        )
    op.execute(
        """CREATE TABLE invatare_stare (
            id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            inghetat boolean NOT NULL DEFAULT false,
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 300),
            schimbat_de uuid REFERENCES utilizatori (id),
            schimbat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute("INSERT INTO invatare_stare (id) VALUES (1)")
    activeaza_rls(op.execute, "invatare_stare")
    op.execute(f"CREATE POLICY invatare_stare_citire ON invatare_stare FOR SELECT USING ({CITIRE})")
    op.execute(
        f"CREATE POLICY invatare_stare_schimbare ON invatare_stare FOR UPDATE USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute("GRANT SELECT, UPDATE ON invatare_stare TO ama_app")


def downgrade() -> None:
    op.execute("DROP TABLE invatare_stare")
    for t in PROTEJATE:
        op.execute(f"DROP TRIGGER {t}_fara_invatare ON {t}")
    op.execute("DROP FUNCTION ama_fara_invatare()")
