"""CRM-ul minimal: firme, contacte, consimțământ, lead-uri, activități, sarcini (F12.1, docs/17 §17.7)

Revizia: 0094
Anterioara: 0093

Date ale agenției (ca `leaduri`): doar contextul de agenție le vede. CRM-ul vândut clienților (date pe client,
cu `tenant_id`) nu e construit aici.

- `crm_firme`, `crm_contacte`: o firmă pe domeniu de site și un contact pe adresă de email (indexuri unice pe
  rândurile neunite), ca același lead trimis de două ori să nu se dubleze. Unirea nu șterge: rândul duplicat
  rămâne, cu `unita_in` / `unit_in` spre cel păstrat.
- `crm_consimtamant`: istoricul consimțământului, doar adăugare (fără UPDATE și DELETE pentru aplicație).
- `crm_leaduri`: un singur lead deschis pe contact; „pierdut” cere motiv.
- `crm_activitati`: urma (note, schimbări de etapă, uniri), doar adăugare.
- `crm_sarcini`: sarcinile de urmărire; cheia unică face crearea automată idempotentă.
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"
ETAPE = "'nou', 'calificat', 'apel_programat', 'oferta_trimisa', 'castigat', 'pierdut'"
TABELE = {
    "crm_firme": "SELECT, INSERT, UPDATE",
    "crm_contacte": "SELECT, INSERT, UPDATE",
    "crm_consimtamant": "SELECT, INSERT",
    "crm_leaduri": "SELECT, INSERT, UPDATE",
    "crm_activitati": "SELECT, INSERT",
    "crm_sarcini": "SELECT, INSERT, UPDATE",
}


def upgrade() -> None:
    op.execute(
        """CREATE TABLE crm_firme (
            id uuid PRIMARY KEY,
            nume text NOT NULL CHECK (length(nume) BETWEEN 2 AND 200),
            nume_norm text NOT NULL CHECK (length(nume_norm) BETWEEN 1 AND 200),
            domeniu text CHECK (domeniu IS NULL OR length(domeniu) BETWEEN 3 AND 253),
            unita_in uuid REFERENCES crm_firme (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            CHECK (unita_in IS NULL OR unita_in <> id)
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX crm_firme_domeniu ON crm_firme (domeniu) "
        "WHERE unita_in IS NULL AND domeniu IS NOT NULL"
    )
    op.execute("CREATE INDEX crm_firme_nume ON crm_firme (nume_norm) WHERE unita_in IS NULL")
    op.execute(
        """CREATE TABLE crm_contacte (
            id uuid PRIMARY KEY,
            firma_id uuid NOT NULL REFERENCES crm_firme (id),
            email text NOT NULL CHECK (length(email) BETWEEN 6 AND 254 AND email = lower(email)),
            nume text NOT NULL DEFAULT '' CHECK (length(nume) <= 200),
            telefon text NOT NULL DEFAULT '' CHECK (length(telefon) <= 40),
            sursa text NOT NULL CHECK (length(sursa) BETWEEN 2 AND 60),
            temei text NOT NULL CHECK (length(temei) BETWEEN 2 AND 60),
            unit_in uuid REFERENCES crm_contacte (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            CHECK (unit_in IS NULL OR unit_in <> id)
        )"""
    )
    op.execute("CREATE UNIQUE INDEX crm_contacte_email ON crm_contacte (email) WHERE unit_in IS NULL")
    op.execute(
        """CREATE TABLE crm_consimtamant (
            id uuid PRIMARY KEY,
            contact_id uuid NOT NULL REFERENCES crm_contacte (id),
            scop text NOT NULL CHECK (length(scop) BETWEEN 2 AND 60),
            acordat boolean NOT NULL,
            sursa text NOT NULL CHECK (length(sursa) BETWEEN 2 AND 60),
            temei text NOT NULL CHECK (length(temei) BETWEEN 2 AND 60),
            dovada text NOT NULL DEFAULT '' CHECK (length(dovada) <= 300),
            la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX crm_consimtamant_contact ON crm_consimtamant (contact_id, scop, la DESC)")
    op.execute(
        f"""CREATE TABLE crm_leaduri (
            id uuid PRIMARY KEY,
            contact_id uuid NOT NULL REFERENCES crm_contacte (id),
            firma_id uuid NOT NULL REFERENCES crm_firme (id),
            sursa text NOT NULL CHECK (length(sursa) BETWEEN 2 AND 60),
            temei text NOT NULL CHECK (length(temei) BETWEEN 2 AND 60),
            etapa text NOT NULL DEFAULT 'nou' CHECK (etapa IN ({ETAPE})),
            motiv_pierdere text NOT NULL DEFAULT '' CHECK (length(motiv_pierdere) <= 300),
            lead_site_id uuid UNIQUE REFERENCES leaduri (id) ON DELETE SET NULL,
            creat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            CHECK (etapa <> 'pierdut' OR length(motiv_pierdere) >= 3)
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX crm_leaduri_deschis ON crm_leaduri (contact_id) "
        "WHERE etapa NOT IN ('castigat', 'pierdut')"
    )
    op.execute(
        """CREATE TABLE crm_activitati (
            id uuid PRIMARY KEY,
            lead_id uuid NOT NULL REFERENCES crm_leaduri (id),
            tip text NOT NULL CHECK (tip IN ('nota', 'etapa', 'unire', 'intrare')),
            text text NOT NULL CHECK (length(text) BETWEEN 1 AND 1000),
            utilizator_id uuid REFERENCES utilizatori (id),
            la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX crm_activitati_lead ON crm_activitati (lead_id, la)")
    op.execute(
        """CREATE TABLE crm_sarcini (
            id uuid PRIMARY KEY,
            lead_id uuid NOT NULL REFERENCES crm_leaduri (id),
            cheie text NOT NULL UNIQUE CHECK (length(cheie) BETWEEN 3 AND 120),
            titlu text NOT NULL CHECK (length(titlu) BETWEEN 3 AND 200),
            scadenta date NOT NULL,
            stare text NOT NULL DEFAULT 'deschisa' CHECK (stare IN ('deschisa', 'facuta', 'anulata')),
            creat_la timestamptz NOT NULL DEFAULT now(),
            inchisa_la timestamptz
        )"""
    )
    op.execute("CREATE INDEX crm_sarcini_deschise ON crm_sarcini (scadenta) WHERE stare = 'deschisa'")
    for tabel, drepturi in TABELE.items():
        activeaza_rls(op.execute, tabel)
        op.execute(f"CREATE POLICY {tabel}_agentie ON {tabel} USING ({AGENTIE}) WITH CHECK ({AGENTIE})")
        op.execute(f"GRANT {drepturi} ON {tabel} TO ama_app")


def downgrade() -> None:
    for tabel in reversed(list(TABELE)):
        op.execute(f"DROP TABLE {tabel}")
