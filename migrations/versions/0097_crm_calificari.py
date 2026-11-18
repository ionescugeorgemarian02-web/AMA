"""Calificare și scor (F12.4, docs/17 §17.5)

Revizia: 0097
Anterioara: 0096

- `crm_calificari`: răspunsurile la cele 4 întrebări de calificare, scorul și grupa (de sunat azi, de hrănit,
  nepotrivit), cu motivele. Doar cu adăugare: o recalificare e un rând nou, starea curentă e ultimul rând.
- `crm_activitati.tip` primește tipurile pașilor F12.4–F12.8 (calificare, programare, ofertă, mesaj).
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"
TIPURI_VECHI = "'nota', 'etapa', 'unire', 'intrare'"
TIPURI_NOI = TIPURI_VECHI + ", 'calificare', 'programare', 'oferta', 'mesaj'"


def _tipuri(lista: str) -> None:
    op.execute("ALTER TABLE crm_activitati DROP CONSTRAINT crm_activitati_tip_check")
    op.execute(f"ALTER TABLE crm_activitati ADD CONSTRAINT crm_activitati_tip_check CHECK (tip IN ({lista}))")


def upgrade() -> None:
    op.execute(
        """CREATE TABLE crm_calificari (
            id uuid PRIMARY KEY,
            lead_id uuid NOT NULL REFERENCES crm_leaduri (id),
            raspunsuri jsonb NOT NULL,
            scor integer NOT NULL CHECK (scor BETWEEN 0 AND 4),
            grupa text NOT NULL CHECK (grupa IN ('suna_azi', 'hraneste', 'nepotrivit')),
            la_om boolean NOT NULL DEFAULT false,
            motive jsonb NOT NULL DEFAULT '[]',
            sursa text NOT NULL CHECK (sursa IN ('formular', 'conversatie', 'manual')),
            la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX crm_calificari_lead ON crm_calificari (lead_id, la DESC)")
    activeaza_rls(op.execute, "crm_calificari")
    op.execute(
        f"CREATE POLICY crm_calificari_agentie ON crm_calificari USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute("GRANT SELECT, INSERT ON crm_calificari TO ama_app")
    _tipuri(TIPURI_NOI)


def downgrade() -> None:
    op.execute(f"DELETE FROM crm_activitati WHERE tip NOT IN ({TIPURI_VECHI})")
    _tipuri(TIPURI_VECHI)
    op.execute("DROP TABLE crm_calificari")
