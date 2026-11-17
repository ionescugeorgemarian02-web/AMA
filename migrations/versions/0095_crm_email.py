"""Email către abonați: lista de suprimare, matricea pe țări, registrul trimiterilor (F12.2, docs/17 §17.3–17.4)

Revizia: 0095
Anterioara: 0094

- `crm_suprimari`: lista globală de suprimare (dezabonați, adrese respinse, plângeri). Aplicația poate doar
  adăuga și citi: o adresă intrată aici nu mai iese prin aplicație.
- `crm_matrice_tari`: ce e permis pe țară și tip de destinatar. România e pusă implicit pe „doar cu
  consimțământ”, inclusiv pentru firme. O țară fără rând este blocată.
- `crm_trimiteri`: emailurile comerciale cerute (o dată pe campanie și contact), pentru limita zilnică și
  pentru ratele de respingere și plângeri.
- `crm_contacte.tara`: țara contactului (implicit România: formularele site-ului sunt în română).
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"
TABELE = {
    "crm_suprimari": "SELECT, INSERT",
    "crm_matrice_tari": "SELECT, INSERT, UPDATE",
    "crm_trimiteri": "SELECT, INSERT",
}


def upgrade() -> None:
    op.execute(
        "ALTER TABLE crm_contacte ADD COLUMN tara text NOT NULL DEFAULT 'RO' CHECK (tara ~ '^[A-Z]{2}$')"
    )
    op.execute(
        """CREATE TABLE crm_suprimari (
            email text PRIMARY KEY CHECK (length(email) BETWEEN 6 AND 254 AND email = lower(email)),
            motiv text NOT NULL CHECK (motiv IN ('dezabonat', 'respins', 'plangere', 'manual')),
            sursa text NOT NULL DEFAULT '' CHECK (length(sursa) <= 120),
            la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX crm_suprimari_la ON crm_suprimari (la)")
    op.execute(
        """CREATE TABLE crm_matrice_tari (
            tara text NOT NULL CHECK (tara ~ '^[A-Z]{2}$'),
            tip_destinatar text NOT NULL CHECK (tip_destinatar IN ('firma', 'persoana')),
            regula text NOT NULL CHECK (regula IN ('doar_cu_consimtamant', 'blocat')),
            mentiuni text NOT NULL DEFAULT '' CHECK (length(mentiuni) <= 500),
            verificat_de text NOT NULL CHECK (length(verificat_de) BETWEEN 3 AND 200),
            verificat_la timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tara, tip_destinatar)
        )"""
    )
    op.execute(
        "INSERT INTO crm_matrice_tari (tara, tip_destinatar, regula, verificat_de) VALUES "
        "('RO', 'firma', 'doar_cu_consimtamant', 'regula implicită din docs/17 §17.4 (neverificată de avocat)'), "
        "('RO', 'persoana', 'doar_cu_consimtamant', 'regula implicită din docs/17 §17.4 (neverificată de avocat)')"
    )
    op.execute(
        """CREATE TABLE crm_trimiteri (
            id uuid PRIMARY KEY,
            contact_id uuid NOT NULL REFERENCES crm_contacte (id),
            email text NOT NULL,
            campanie text NOT NULL CHECK (length(campanie) BETWEEN 2 AND 80),
            cheie text NOT NULL UNIQUE,
            la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX crm_trimiteri_la ON crm_trimiteri (la)")
    for tabel, drepturi in TABELE.items():
        activeaza_rls(op.execute, tabel)
        op.execute(f"CREATE POLICY {tabel}_agentie ON {tabel} USING ({AGENTIE}) WITH CHECK ({AGENTIE})")
        op.execute(f"GRANT {drepturi} ON {tabel} TO ama_app")


def downgrade() -> None:
    for tabel in reversed(list(TABELE)):
        op.execute(f"DROP TABLE {tabel}")
    op.execute("ALTER TABLE crm_contacte DROP COLUMN tara")
