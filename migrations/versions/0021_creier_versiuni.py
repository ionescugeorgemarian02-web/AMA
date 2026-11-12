"""Creierul de brand: intrări versionate (F4.1, docs/10, docs/20 §20.1–20.2)

Revizia: 0021
Anterioara: 0020

- `creier_intrari`: identitatea unei intrări (un compartiment din 10.1, o cheie, un nivel din 10.2). Nu se modifică și nu se
  șterge (aplicația nu are drepturile). `tenant_id` lipsește DOAR la nivelurile `nisa` / `platforma` (tipare agregate,
  anonimizate): le citește orice context autentificat, le scrie doar agenția.
- `creier_versiuni`: versiunile unei intrări. Conținutul, sursa și valabilitatea unei versiuni NU se mai schimbă după
  creare (declanșator în bază): se schimbă doar starea (`ciorna` → `propus` → `aprobat` → `retras`) și urmele ei (cine și
  când a aprobat / retras). Cel mult o versiune aprobată pe intrare (index unic parțial). Sursa e obligatorie.
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

TENANT_SAU_AGENTIE = "(tenant_id = (SELECT ama_tenant_id()) OR (SELECT ama_agency()))"
CITIRE = (
    "(tenant_id = (SELECT ama_tenant_id()) OR (SELECT ama_agency()) "
    "OR (tenant_id IS NULL AND ((SELECT ama_tenant_id()) IS NOT NULL OR (SELECT ama_user_id()) IS NOT NULL)))"
)
IMUTABILE = (
    "id", "intrare_id", "tenant_id", "nr", "continut", "text_cautare", "sursa_tip", "sursa_ref", "sursa_citat",
    "sursa_detalii", "valabil_de_la", "valabil_pana_la", "motiv", "creat_de", "creat_la",
)  # fmt: skip


def upgrade() -> None:
    op.execute(
        """CREATE TABLE creier_intrari (
            id uuid PRIMARY KEY,
            tenant_id uuid REFERENCES clienti (id),
            nivel text NOT NULL DEFAULT 'client' CHECK (nivel IN ('client', 'nisa', 'platforma')),
            compartiment text NOT NULL CHECK (compartiment ~ '^[a-z][a-z_]{2,39}$'),
            cheie text NOT NULL CHECK (cheie ~ '^[a-z0-9][a-z0-9_.:-]{0,79}$'),
            creat_la timestamptz NOT NULL DEFAULT now(),
            creat_de uuid REFERENCES utilizatori (id),
            CONSTRAINT creier_intrari_nivel_client CHECK ((nivel = 'client') = (tenant_id IS NOT NULL))
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX creier_intrari_cheie ON creier_intrari "
        "(COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid), nivel, compartiment, cheie)"
    )
    op.execute("CREATE INDEX creier_intrari_client ON creier_intrari (tenant_id, compartiment)")
    _rls("creier_intrari", "SELECT, INSERT")

    op.execute(
        """CREATE TABLE creier_versiuni (
            id uuid PRIMARY KEY,
            intrare_id uuid NOT NULL REFERENCES creier_intrari (id),
            tenant_id uuid REFERENCES clienti (id),
            nr integer NOT NULL CHECK (nr >= 1),
            continut jsonb NOT NULL CHECK (jsonb_typeof(continut) = 'object'),
            text_cautare text NOT NULL DEFAULT '' CHECK (length(text_cautare) <= 4000),
            stare text NOT NULL CHECK (stare IN ('ciorna', 'propus', 'aprobat', 'retras')),
            sursa_tip text NOT NULL CHECK (
                sursa_tip IN ('declaratie_client', 'document', 'pasaj', 'url', 'om', 'sistem', 'agregat')),
            sursa_ref text CHECK (length(sursa_ref) BETWEEN 1 AND 2000),
            sursa_citat text CHECK (length(sursa_citat) <= 4000),
            sursa_detalii jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(sursa_detalii) = 'object'),
            valabil_de_la timestamptz,
            valabil_pana_la timestamptz,
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 500),
            creat_de uuid REFERENCES utilizatori (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            propus_la timestamptz,
            aprobat_de uuid REFERENCES utilizatori (id),
            aprobat_la timestamptz,
            aprobat_prin text CHECK (aprobat_prin IN ('om', 'sistem')),
            retras_de uuid REFERENCES utilizatori (id),
            retras_la timestamptz,
            retras_cauza text CHECK (retras_cauza IN ('retras', 'respins', 'inlocuita', 'expirat')),
            retras_motiv text NOT NULL DEFAULT '' CHECK (length(retras_motiv) <= 500),
            inlocuita_de integer,
            UNIQUE (intrare_id, nr),
            CONSTRAINT creier_versiuni_valabilitate CHECK (
                valabil_de_la IS NULL OR valabil_pana_la IS NULL OR valabil_pana_la > valabil_de_la),
            CONSTRAINT creier_versiuni_sursa_referinta CHECK (
                sursa_tip NOT IN ('document', 'pasaj', 'url') OR sursa_ref IS NOT NULL),
            CONSTRAINT creier_versiuni_sursa_autor CHECK (
                sursa_tip NOT IN ('declaratie_client', 'om') OR creat_de IS NOT NULL),
            CONSTRAINT creier_versiuni_aprobare CHECK (
                stare <> 'aprobat' OR (aprobat_la IS NOT NULL AND aprobat_prin IS NOT NULL
                                       AND (aprobat_prin <> 'om' OR aprobat_de IS NOT NULL))),
            CONSTRAINT creier_versiuni_retragere CHECK (
                stare <> 'retras' OR (retras_la IS NOT NULL AND retras_cauza IS NOT NULL)),
            CONSTRAINT creier_versiuni_propunere CHECK (stare = 'ciorna' OR propus_la IS NOT NULL OR stare = 'retras')
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX creier_versiuni_aprobata ON creier_versiuni (intrare_id) WHERE stare = 'aprobat'"
    )
    op.execute("CREATE INDEX creier_versiuni_client ON creier_versiuni (tenant_id, stare)")
    _rls("creier_versiuni", "SELECT, INSERT, UPDATE")

    conditii = " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in IMUTABILE)
    op.execute(
        f"""CREATE FUNCTION creier_versiuni_imutabila() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF {conditii} THEN
                RAISE EXCEPTION 'o versiune a Creierului nu se modifică: se creează una nouă' USING ERRCODE = '23514';
            END IF;
            IF OLD.stare = NEW.stare THEN
                IF NEW IS DISTINCT FROM OLD THEN
                    RAISE EXCEPTION 'starea versiunii nu s-a schimbat, deci nimic altceva nu se modifică'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;
            IF NOT (   (OLD.stare = 'ciorna' AND NEW.stare IN ('propus', 'retras'))
                    OR (OLD.stare = 'propus'  AND NEW.stare IN ('aprobat', 'retras'))
                    OR (OLD.stare = 'aprobat' AND NEW.stare = 'retras')) THEN
                RAISE EXCEPTION 'tranziție nepermisă: % -> %', OLD.stare, NEW.stare USING ERRCODE = '23514';
            END IF;
            IF (OLD.propus_la IS NOT NULL AND NEW.propus_la IS DISTINCT FROM OLD.propus_la)
               OR (OLD.aprobat_la IS NOT NULL AND (NEW.aprobat_la IS DISTINCT FROM OLD.aprobat_la
                   OR NEW.aprobat_de IS DISTINCT FROM OLD.aprobat_de
                   OR NEW.aprobat_prin IS DISTINCT FROM OLD.aprobat_prin)) THEN
                RAISE EXCEPTION 'urmele unei stări deja parcurse nu se rescriu' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER creier_versiuni_imutabila BEFORE UPDATE ON creier_versiuni "
        "FOR EACH ROW EXECUTE FUNCTION creier_versiuni_imutabila()"
    )
    op.execute(
        """CREATE FUNCTION creier_versiuni_la_inserare() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.stare NOT IN ('ciorna', 'propus') THEN
                RAISE EXCEPTION 'o versiune nouă începe ciornă sau propusă' USING ERRCODE = '23514';
            END IF;
            IF NEW.tenant_id IS DISTINCT FROM (SELECT tenant_id FROM creier_intrari WHERE id = NEW.intrare_id) THEN
                RAISE EXCEPTION 'versiunea trebuie să aibă clientul intrării' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER creier_versiuni_la_inserare BEFORE INSERT ON creier_versiuni "
        "FOR EACH ROW EXECUTE FUNCTION creier_versiuni_la_inserare()"
    )


def _rls(tabel: str, drepturi: str) -> None:
    activeaza_rls(op.execute, tabel)
    op.execute(f"CREATE POLICY {tabel}_citire ON {tabel} FOR SELECT USING {CITIRE}")
    op.execute(f"CREATE POLICY {tabel}_adaugare ON {tabel} FOR INSERT WITH CHECK {TENANT_SAU_AGENTIE}")
    if "UPDATE" in drepturi:
        op.execute(
            f"CREATE POLICY {tabel}_schimbare ON {tabel} FOR UPDATE "
            f"USING {TENANT_SAU_AGENTIE} WITH CHECK {TENANT_SAU_AGENTIE}"
        )
    op.execute(f"GRANT {drepturi} ON {tabel} TO ama_app")


def downgrade() -> None:
    op.execute("DROP TABLE creier_versiuni")
    op.execute("DROP FUNCTION creier_versiuni_imutabila()")
    op.execute("DROP FUNCTION creier_versiuni_la_inserare()")
    op.execute("DROP TABLE creier_intrari")
