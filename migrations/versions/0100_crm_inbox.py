"""Inboxul social (F12.7, docs/17 §17.8)

Revizia: 0100
Anterioara: 0099

- `crm_inbox_canale`: canalele de pe care se citesc mesaje (doar cele aprobate de proprietar), cu momentul
  până la care s-a citit.
- `crm_inbox_mesaje`: mesajele și comentariile citite, o singură dată pe canal și id extern, cu clasa dată de
  reguli (întrebare, cerere de preț, laudă, critică, subiect sensibil, spam, neclar) și starea tratării.
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"
CLASE = "'intrebare', 'cerere_pret', 'lauda', 'critica', 'sensibil', 'spam', 'neclar'"
TABELE = {"crm_inbox_canale": "SELECT, INSERT, UPDATE", "crm_inbox_mesaje": "SELECT, INSERT, UPDATE"}


def upgrade() -> None:
    op.execute(
        """CREATE TABLE crm_inbox_canale (
            canal text PRIMARY KEY CHECK (canal IN ('instagram', 'facebook')),
            aprobat_de uuid NOT NULL REFERENCES utilizatori (id),
            aprobat_la timestamptz NOT NULL DEFAULT now(),
            activ boolean NOT NULL DEFAULT true,
            citit_pana_la timestamptz
        )"""
    )
    op.execute(
        f"""CREATE TABLE crm_inbox_mesaje (
            id uuid PRIMARY KEY,
            canal text NOT NULL REFERENCES crm_inbox_canale (canal),
            id_extern text NOT NULL CHECK (length(id_extern) BETWEEN 1 AND 200),
            tip text NOT NULL CHECK (tip IN ('mesaj', 'comentariu')),
            fir text NOT NULL CHECK (length(fir) BETWEEN 1 AND 200),
            autor text NOT NULL CHECK (length(autor) BETWEEN 1 AND 200),
            text text NOT NULL CHECK (length(text) <= 4000),
            primit_la timestamptz NOT NULL,
            clasa text NOT NULL CHECK (clasa IN ({CLASE})),
            motiv_clasa text NOT NULL DEFAULT '' CHECK (length(motiv_clasa) <= 200),
            stare text NOT NULL DEFAULT 'nou'
                CHECK (stare IN ('nou', 'raspuns', 'propus', 'la_om', 'ascuns', 'inchis')),
            citit_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (canal, id_extern)
        )"""
    )
    op.execute("CREATE INDEX crm_inbox_mesaje_fir ON crm_inbox_mesaje (canal, fir, primit_la DESC)")
    for tabel, drepturi in TABELE.items():
        activeaza_rls(op.execute, tabel)
        op.execute(f"CREATE POLICY {tabel}_agentie ON {tabel} USING ({AGENTIE}) WITH CHECK ({AGENTIE})")
        op.execute(f"GRANT {drepturi} ON {tabel} TO ama_app")


def downgrade() -> None:
    for tabel in reversed(list(TABELE)):
        op.execute(f"DROP TABLE {tabel}")
