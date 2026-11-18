"""Răspunsuri și escaladare în inboxul social (F12.8, docs/17 §17.8)

Revizia: 0101
Anterioara: 0100

- `crm_inbox_raspunsuri`: răspunsurile propuse sau trimise (de sistem sau de om), cu motivul unui blocaj
  (în afara ferestrei de mesagerie, clasă care cere om). Eticheta „agent uman” doar pe răspunsurile scrise de om.
- `crm_inbox_canale.nivel`: nivelul de autonomie al canalului (L0–L4, implicit L1: totul se propune).
- `crm_inbox_mesaje.de_verificat`: eșantionul de spam ascuns automat, pe care îl verifică un om.
- `efecte_sistem.tip` primește `mesaj_social` (răspunsul și ascunderea trec prin executorul de efecte).
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"


def _tipuri_efecte(lista: str) -> None:
    op.execute("ALTER TABLE efecte_sistem DROP CONSTRAINT efecte_sistem_tip_check")
    op.execute(f"ALTER TABLE efecte_sistem ADD CONSTRAINT efecte_sistem_tip_check CHECK (tip IN ({lista}))")


def upgrade() -> None:
    _tipuri_efecte("'email', 'plata', 'reclama', 'mesaj_social'")
    op.execute(
        "ALTER TABLE crm_inbox_canale ADD COLUMN nivel text NOT NULL DEFAULT 'L1' "
        "CHECK (nivel IN ('L0', 'L1', 'L2', 'L3', 'L4'))"
    )
    op.execute("ALTER TABLE crm_inbox_mesaje ADD COLUMN de_verificat boolean NOT NULL DEFAULT false")
    op.execute(
        """CREATE TABLE crm_inbox_raspunsuri (
            id uuid PRIMARY KEY,
            mesaj_id uuid NOT NULL REFERENCES crm_inbox_mesaje (id),
            text text NOT NULL CHECK (length(text) BETWEEN 1 AND 2000),
            autor text NOT NULL CHECK (autor IN ('sistem', 'om')),
            utilizator_id uuid REFERENCES utilizatori (id),
            stare text NOT NULL CHECK (stare IN ('propus', 'trimis', 'blocat', 'inlocuit')),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 200),
            eticheta_agent_uman boolean NOT NULL DEFAULT false CHECK (NOT eticheta_agent_uman OR autor = 'om'),
            creat_la timestamptz NOT NULL DEFAULT now(),
            trimis_la timestamptz
        )"""
    )
    op.execute("CREATE INDEX crm_inbox_raspunsuri_mesaj ON crm_inbox_raspunsuri (mesaj_id)")
    activeaza_rls(op.execute, "crm_inbox_raspunsuri")
    op.execute(
        "CREATE POLICY crm_inbox_raspunsuri_agentie ON crm_inbox_raspunsuri "
        f"USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON crm_inbox_raspunsuri TO ama_app")


def downgrade() -> None:
    op.execute("DROP TABLE crm_inbox_raspunsuri")
    op.execute("ALTER TABLE crm_inbox_mesaje DROP COLUMN de_verificat")
    op.execute("ALTER TABLE crm_inbox_canale DROP COLUMN nivel")
    op.execute("DELETE FROM efecte_sistem WHERE tip = 'mesaj_social'")
    _tipuri_efecte("'email', 'plata', 'reclama'")
