"""Învățare: registrul de experimente (F11.4, K7, docs/11 §11.2 N7, §11.6)

Revizia: 0092
Anterioara: 0091

- `experimente`: ipoteza, cele două variante ale unei dimensiuni, indicatorul și regula de oprire, toate
  declarate DINAINTE; apoi starea și rezultatul. Un declanșator împiedică schimbarea celor declarate după
  creare. Un singur experiment în curs pe client și dimensiune, ca efectul să poată fi atribuit (11.6).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE experimente (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            ipoteza text NOT NULL CHECK (length(ipoteza) BETWEEN 10 AND 400),
            dimensiune text NOT NULL CHECK (dimensiune IN ('tipar_hook', 'slot', 'format', 'canal')),
            varianta_a text NOT NULL CHECK (length(varianta_a) BETWEEN 1 AND 80),
            varianta_b text NOT NULL CHECK (length(varianta_b) BETWEEN 1 AND 80),
            indicator text NOT NULL CHECK (indicator IN ('interactiuni_pe_afisari', 'retentie_medie')),
            minim_pe_varianta integer NOT NULL CHECK (minim_pe_varianta BETWEEN 2 AND 1000),
            prag_diferenta real NOT NULL CHECK (prag_diferenta > 0 AND prag_diferenta <= 5),
            durata_maxima_zile integer NOT NULL CHECK (durata_maxima_zile BETWEEN 1 AND 365),
            stare text NOT NULL DEFAULT 'in_curs' CHECK (stare IN ('in_curs', 'incheiat', 'oprit')),
            concluzie text CHECK (concluzie IN ('castiga_a', 'castiga_b', 'fara_diferenta', 'neconcludent')),
            rezultat jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(rezultat) = 'object'),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 300),
            inceput_la timestamptz NOT NULL DEFAULT now(),
            incheiat_la timestamptz,
            creat_de uuid REFERENCES utilizatori (id),
            CHECK (varianta_a <> varianta_b),
            CHECK ((stare = 'incheiat') = (concluzie IS NOT NULL)),
            CHECK ((stare = 'in_curs') = (incheiat_la IS NULL))
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX experimente_unul_in_curs ON experimente (tenant_id, dimensiune) WHERE stare = 'in_curs'"
    )
    op.execute(
        """CREATE FUNCTION experimente_protejeaza() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (NEW.tenant_id, NEW.ipoteza, NEW.dimensiune, NEW.varianta_a, NEW.varianta_b, NEW.indicator,
                NEW.minim_pe_varianta, NEW.prag_diferenta, NEW.durata_maxima_zile, NEW.inceput_la)
               IS DISTINCT FROM
               (OLD.tenant_id, OLD.ipoteza, OLD.dimensiune, OLD.varianta_a, OLD.varianta_b, OLD.indicator,
                OLD.minim_pe_varianta, OLD.prag_diferenta, OLD.durata_maxima_zile, OLD.inceput_la) THEN
                RAISE EXCEPTION 'ce s-a declarat la pornirea experimentului nu se mai schimbă' USING ERRCODE = '23514';
            END IF;
            IF OLD.stare <> 'in_curs' THEN
                RAISE EXCEPTION 'un experiment încheiat nu se mai schimbă' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER experimente_protejat BEFORE UPDATE ON experimente "
        "FOR EACH ROW EXECUTE FUNCTION experimente_protejeaza()"
    )
    activeaza_rls_tenant(op.execute, "experimente")


def downgrade() -> None:
    op.execute("DROP TABLE experimente")
    op.execute("DROP FUNCTION experimente_protejeaza()")
