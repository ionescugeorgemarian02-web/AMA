"""Gateway de modele: registrul de prompturi și jurnalul de apeluri (F3.7, docs/08 §8.8, docs/20 §20.4)

Revizia: 0015
Anterioara: 0014

- `gateway_prompturi`: prompturi versionate (nume, versiune, șablon, schemă de ieșire, profil, stare: ciornă / activ /
  retras). Registru la nivel de agenție. O versiune care nu mai e ciornă nu se mai modifică (declanșator): se creează
  una nouă. Cel mult o versiune activă pe nume (index unic parțial). Fără DELETE: istoricul rămâne.
- `gateway_apeluri`: jurnalul de apeluri, cu `tenant_id` și RLS: cine (client, livrabil, componentă), ce prompt și ce
  versiune, ce model și de ce, tokeni, durată, rezultat, reparații, preț-umbră, traseul încercărilor. Doar adăugări;
  metadatele se păstrează.
- `gateway_apeluri_continut`: CONȚINUTUL (mesajele trimise, după mascare, și răspunsul validat), separat de metadate,
  cu `tenant_id`, RLS și `expira_la` (30 de zile, apoi se șterge; 20.4). Nu stă în tabelele motorului și nu intră în
  jurnalele aplicației.
"""

from alembic import op

from app.db.rls import activeaza_rls, activeaza_rls_tenant

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"
CITIRE = (
    "((SELECT ama_agency()) OR (SELECT ama_tenant_id()) IS NOT NULL OR (SELECT ama_user_id()) IS NOT NULL)"
)
TRANZITII = "(('ciorna', 'activ'), ('ciorna', 'retras'), ('activ', 'retras'))"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE gateway_prompturi (
            id uuid PRIMARY KEY,
            nume text NOT NULL CHECK (nume ~ '^[a-z][a-z0-9_.]{1,60}$'),
            versiune integer NOT NULL CHECK (versiune >= 1),
            stare text NOT NULL DEFAULT 'ciorna' CHECK (stare IN ('ciorna', 'activ', 'retras')),
            profil text NOT NULL CHECK (profil ~ '^[a-z][a-z0-9_]{1,40}$'),
            sistem text NOT NULL DEFAULT '' CHECK (length(sistem) <= 20000),
            sablon text NOT NULL CHECK (length(sablon) BETWEEN 1 AND 20000),
            schema_nume text NOT NULL CHECK (length(schema_nume) BETWEEN 1 AND 200),
            schema_json jsonb NOT NULL,
            descriere text NOT NULL DEFAULT '' CHECK (length(descriere) <= 500),
            amprenta text NOT NULL CHECK (amprenta ~ '^[0-9a-f]{64}$'),
            creat_la timestamptz NOT NULL DEFAULT now(),
            creat_de uuid REFERENCES utilizatori (id),
            activat_la timestamptz,
            retras_la timestamptz,
            CONSTRAINT prompt_versiune_unica UNIQUE (nume, versiune)
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX gateway_prompturi_un_activ ON gateway_prompturi (nume) WHERE stare = 'activ'"
    )
    op.execute(
        f"""CREATE FUNCTION ama_prompt_garda() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.stare <> 'ciorna' AND (
                (NEW.id, NEW.nume, NEW.versiune, NEW.profil, NEW.sistem, NEW.sablon, NEW.schema_nume,
                 NEW.schema_json, NEW.amprenta)
                IS DISTINCT FROM
                (OLD.id, OLD.nume, OLD.versiune, OLD.profil, OLD.sistem, OLD.sablon, OLD.schema_nume,
                 OLD.schema_json, OLD.amprenta)) THEN
                RAISE EXCEPTION 'promptul % versiunea % nu se modifică: creează o versiune nouă', OLD.nume, OLD.versiune
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF NEW.stare <> OLD.stare AND (OLD.stare, NEW.stare) NOT IN {TRANZITII} THEN
                RAISE EXCEPTION 'tranziție nepermisă a promptului % v%: % -> %', OLD.nume, OLD.versiune, OLD.stare, NEW.stare
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER gateway_prompturi_garda BEFORE UPDATE ON gateway_prompturi "
        "FOR EACH ROW EXECUTE FUNCTION ama_prompt_garda()"
    )
    activeaza_rls(op.execute, "gateway_prompturi")
    op.execute(f"CREATE POLICY gateway_prompturi_citire ON gateway_prompturi FOR SELECT USING ({CITIRE})")
    op.execute(
        f"CREATE POLICY gateway_prompturi_adaugare ON gateway_prompturi FOR INSERT WITH CHECK ({AGENTIE})"
    )
    op.execute(
        f"CREATE POLICY gateway_prompturi_schimbare ON gateway_prompturi FOR UPDATE USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON gateway_prompturi TO ama_app")

    op.execute(
        """CREATE TABLE gateway_apeluri (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid,
            componenta text NOT NULL CHECK (length(componenta) BETWEEN 1 AND 100),
            prioritate text NOT NULL CHECK (prioritate IN ('P0', 'P1', 'P2', 'P3')),
            profil text NOT NULL DEFAULT '' CHECK (length(profil) <= 60),
            prompt_nume text NOT NULL DEFAULT '' CHECK (length(prompt_nume) <= 100),
            prompt_versiune integer,
            furnizor text NOT NULL DEFAULT '' CHECK (length(furnizor) <= 40),
            model text NOT NULL DEFAULT '' CHECK (length(model) <= 250),
            nivel text NOT NULL DEFAULT '' CHECK (length(nivel) <= 10),
            motiv_alegere text NOT NULL DEFAULT '' CHECK (length(motiv_alegere) <= 300),
            rezultat text NOT NULL CHECK (rezultat IN ('ok', 'esec', 'amanat', 'refuzat')),
            cod_eroare text NOT NULL DEFAULT '' CHECK (length(cod_eroare) <= 100),
            tokeni_intrare integer NOT NULL DEFAULT 0 CHECK (tokeni_intrare >= 0),
            tokeni_iesire integer NOT NULL DEFAULT 0 CHECK (tokeni_iesire >= 0),
            durata_ms integer NOT NULL DEFAULT 0 CHECK (durata_ms >= 0),
            reparatii smallint NOT NULL DEFAULT 0 CHECK (reparatii >= 0),
            pret_umbra numeric(12, 6) NOT NULL DEFAULT 0 CHECK (pret_umbra >= 0),
            degradat boolean NOT NULL DEFAULT false,
            provizoriu boolean NOT NULL DEFAULT false,
            verificare_suplimentara boolean NOT NULL DEFAULT false,
            incercari jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (octet_length(incercari::text) <= 16384),
            corelare_id text NOT NULL DEFAULT '' CHECK (length(corelare_id) <= 100),
            creat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX gateway_apeluri_client ON gateway_apeluri (tenant_id, creat_la DESC)")
    op.execute("CREATE INDEX gateway_apeluri_model ON gateway_apeluri (tenant_id, model, creat_la DESC)")
    op.execute(
        "CREATE INDEX gateway_apeluri_livrabil ON gateway_apeluri (livrabil_id) WHERE livrabil_id IS NOT NULL"
    )
    activeaza_rls_tenant(op.execute, "gateway_apeluri", drepturi="SELECT, INSERT")

    op.execute(
        """CREATE TABLE gateway_apeluri_continut (
            apel_id uuid PRIMARY KEY REFERENCES gateway_apeluri (id),
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            mesaje jsonb NOT NULL,
            raspuns jsonb,
            expira_la timestamptz NOT NULL
        )"""
    )
    op.execute("CREATE INDEX gateway_apeluri_continut_expirare ON gateway_apeluri_continut (expira_la)")
    activeaza_rls_tenant(op.execute, "gateway_apeluri_continut", drepturi="SELECT, INSERT, DELETE")


def downgrade() -> None:
    op.execute("DROP TABLE gateway_apeluri_continut")
    op.execute("DROP TABLE gateway_apeluri")
    op.execute("DROP TABLE gateway_prompturi")
    op.execute("DROP FUNCTION ama_prompt_garda()")
