"""Validare: bancul de evaluare și exemplele propuse pentru setul de aur (F5.7, docs/09 §9.9, docs/11 N1)

Revizia: 0031
Anterioara: 0030

- `banc_rulari`: o rulare a bancului (K4) peste seturile de aur: cine a pornit-o, când, starea, amprenta seturilor și scorurile
  (JSON). Nivel de agenție (fără `tenant_id`): seturile sunt ale platformei, nu ale unui client.
- `exemple_propuse`: exemplele propuse pentru setul de aur, venite dintr-o contestație (F5.10) sau dintr-o etichetă umană (F5.8).
  Pe client (conțin textul unui livrabil), cu RLS. Un om le promovează sau le respinge; un exemplu PROMOVAT intră în rularea
  bancului. Nu se scriu automat în depozitul git (`evaluare/aur/`): promovarea înseamnă decizia unui om, iar exportul în depozit
  este tot un gest uman.
"""

from alembic import op

from app.db.rls import activeaza_rls, activeaza_rls_tenant

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE banc_rulari (
            id uuid PRIMARY KEY,
            cheie text UNIQUE CHECK (cheie IS NULL OR length(cheie) BETWEEN 1 AND 120),
            pornit_de uuid REFERENCES utilizatori (id),
            pornit_la timestamptz NOT NULL DEFAULT now(),
            terminat_la timestamptz,
            stare text NOT NULL DEFAULT 'in_curs' CHECK (stare IN ('in_curs', 'terminat', 'esuat')),
            amprenta_seturi text NOT NULL DEFAULT '' CHECK (length(amprenta_seturi) <= 64),
            exemple integer NOT NULL DEFAULT 0 CHECK (exemple >= 0),
            scoruri jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(scoruri) = 'object'),
            eroare text NOT NULL DEFAULT '' CHECK (length(eroare) <= 500)
        )"""
    )
    op.execute("CREATE INDEX banc_rulari_recente ON banc_rulari (pornit_la DESC)")
    activeaza_rls(op.execute, "banc_rulari")
    op.execute(f"CREATE POLICY banc_rulari_agentie ON banc_rulari USING ({AGENTIE}) WITH CHECK ({AGENTIE})")
    op.execute("GRANT SELECT, INSERT, UPDATE ON banc_rulari TO ama_app")

    op.execute(
        """CREATE TABLE exemple_propuse (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            validator text NOT NULL CHECK (validator ~ '^[A-Z][A-Z0-9_]{0,15}$'),
            sursa text NOT NULL CHECK (sursa IN ('contestatie', 'eticheta')),
            verdict_id uuid NOT NULL REFERENCES validari_verdicte (id),
            livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            versiune integer NOT NULL CHECK (versiune >= 1),
            tip text NOT NULL,
            canal text NOT NULL,
            text text NOT NULL CHECK (length(text) BETWEEN 1 AND 20000),
            campuri jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(campuri) = 'object'),
            active jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(active) = 'array'),
            asteptat text NOT NULL CHECK (asteptat IN ('trece', 'esec')),
            severitate text CHECK (severitate IN ('majora', 'critica')),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 500),
            stare text NOT NULL DEFAULT 'propus' CHECK (stare IN ('propus', 'promovat', 'respins')),
            context_profil text NOT NULL DEFAULT 'gol' CHECK (context_profil ~ '^[a-z][a-z0-9_]{0,40}$'),
            decis_de uuid REFERENCES utilizatori (id),
            decis_la timestamptz,
            motiv_decizie text NOT NULL DEFAULT '' CHECK (length(motiv_decizie) <= 500),
            creat_de uuid REFERENCES utilizatori (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (verdict_id, sursa),
            CHECK ((asteptat = 'esec') = (severitate IS NOT NULL)),
            CHECK ((stare = 'propus') = (decis_la IS NULL))
        )"""
    )
    op.execute("CREATE INDEX exemple_propuse_stare ON exemple_propuse (stare, creat_la)")
    op.execute("CREATE INDEX exemple_propuse_validator ON exemple_propuse (validator, stare)")
    activeaza_rls_tenant(op.execute, "exemple_propuse", drepturi="SELECT, INSERT, UPDATE")
    # Exemplul are clientul verdictului din care vine (subinterogarea vede doar rândurile clientului curent: verdictul altui
    # client dă NULL, deci refuz), iar legătura lui (client, verdict, validator, sursă) nu se rescrie după inserare.
    op.execute(
        """CREATE FUNCTION exemple_propuse_verifica() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' AND NEW.tenant_id IS DISTINCT FROM
                    (SELECT tenant_id FROM validari_verdicte WHERE id = NEW.verdict_id) THEN
                RAISE EXCEPTION 'exemplul trebuie să aibă clientul verdictului' USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'UPDATE' AND (NEW.tenant_id, NEW.verdict_id, NEW.validator, NEW.sursa, NEW.livrabil_id, NEW.versiune)
                    IS DISTINCT FROM (OLD.tenant_id, OLD.verdict_id, OLD.validator, OLD.sursa, OLD.livrabil_id, OLD.versiune) THEN
                RAISE EXCEPTION 'legătura exemplului cu verdictul nu se schimbă' USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'UPDATE' AND OLD.stare <> 'propus' THEN
                RAISE EXCEPTION 'un exemplu decis nu se mai schimbă' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER exemple_propuse_verifica BEFORE INSERT OR UPDATE ON exemple_propuse "
        "FOR EACH ROW EXECUTE FUNCTION exemple_propuse_verifica()"
    )


def downgrade() -> None:
    op.execute("DROP TABLE exemple_propuse")
    op.execute("DROP FUNCTION exemple_propuse_verifica()")
    op.execute("DROP TABLE banc_rulari")
