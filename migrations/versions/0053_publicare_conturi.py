"""Publicarea prin API: conturile canalelor și aprobările platformelor (F9.1, docs/15 §15.1–§15.3)

Revizia: 0053
Anterioara: 0052

- `publicare_conturi`: contul unui client pe un canal (id-ul extern, dacă e contul agenției, modul ales de om,
tokenul
  CRIPTAT cu `AMA_MASTER_KEY` și expirarea lui, starea OAuth în curs ca HMAC, setările canalului). Izolat prin
  RLS.
- `aprobari_api`: aprobările aplicației agenției la platforme (App Review, audit), pe permisiune. Date de
agenție, nu
  de client: oricine autentificat citește, doar agenția scrie (ca `gateway_contoare`).
"""

from alembic import op

from app.db.rls import activeaza_rls, activeaza_rls_tenant

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"
CITIRE = (
    "((SELECT ama_agency()) OR (SELECT ama_tenant_id()) IS NOT NULL OR (SELECT ama_user_id()) IS NOT NULL)"
)
# platforma, permisiunea, starea inițială: aplicațiile sunt în modul de test (doar conturile agenției),
# profilul
# LinkedIn e self-serve (15.1: „automat de la început, pe profilul tău”).
APROBARI = (
    ("meta", "pagini", "in_test"),
    ("meta", "instagram", "in_test"),
    ("google", "youtube", "in_test"),
    ("linkedin", "profil", "aprobata"),
    ("linkedin", "pagina", "in_test"),
    ("tiktok", "publicare", "in_test"),
)


def upgrade() -> None:
    op.execute(
        """CREATE TABLE publicare_conturi (
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            canal text NOT NULL CHECK (canal ~ '^[a-z][a-z0-9_]{1,39}$'),
            cont_extern text NOT NULL DEFAULT '' CHECK (length(cont_extern) <= 200),
            nume text NOT NULL DEFAULT '' CHECK (length(nume) <= 200),
            cont_agentie boolean NOT NULL DEFAULT false,
            mod_ales text NOT NULL DEFAULT 'automat' CHECK (mod_ales IN ('asistat', 'automat')),
            token_criptat bytea,
            expira_la timestamptz,
            scopuri text[] NOT NULL DEFAULT '{}',
            stare_oauth bytea,
            autorizat_la timestamptz,
            cere_reautorizare boolean NOT NULL DEFAULT false,
            setari jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(setari) = 'object'),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, canal)
        )"""
    )
    activeaza_rls_tenant(op.execute, "publicare_conturi")
    op.execute(
        """CREATE TABLE aprobari_api (
            platforma text NOT NULL CHECK (platforma ~ '^[a-z][a-z0-9_]{1,30}$'),
            permisiune text NOT NULL CHECK (permisiune ~ '^[a-z][a-z0-9_]{1,40}$'),
            stare text NOT NULL CHECK (stare IN ('neceruta', 'in_test', 'trimisa', 'aprobata', 'respinsa')),
            inregistrare text CHECK (length(inregistrare) <= 500),
            trimisa_la timestamptz,
            decisa_la timestamptz,
            observatii text NOT NULL DEFAULT '' CHECK (length(observatii) <= 2000),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (platforma, permisiune),
            CHECK (stare NOT IN ('trimisa', 'aprobata', 'respinsa') OR permisiune = 'profil' OR inregistrare
            IS NOT NULL)
        )"""
    )
    activeaza_rls(op.execute, "aprobari_api")
    op.execute(f"CREATE POLICY aprobari_api_citire ON aprobari_api FOR SELECT USING ({CITIRE})")
    op.execute(f"CREATE POLICY aprobari_api_adaugare ON aprobari_api FOR INSERT WITH CHECK ({AGENTIE})")
    op.execute(
        f"CREATE POLICY aprobari_api_schimbare ON aprobari_api FOR UPDATE USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON aprobari_api TO ama_app")
    op.execute("SELECT set_config('app.agency', '1', true)")
    for platforma, permisiune, stare in APROBARI:
        op.execute(
            f"INSERT INTO aprobari_api (platforma, permisiune, stare) VALUES ('{platforma}', '{permisiune}', '{stare}')"
        )


def downgrade() -> None:
    op.execute("DROP TABLE aprobari_api")
    op.execute("DROP TABLE publicare_conturi")
