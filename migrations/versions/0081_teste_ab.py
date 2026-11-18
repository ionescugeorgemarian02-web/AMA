"""Învățare: testele A/B formale (F14.4, docs/11 §11.2 N7), legate de măsurarea promovărilor (F14.2)

Revizia: 0081
Anterioara: 0080

- `teste_ab`: ipoteza, obiectul, cele două variante (A = control), indicatorul, efectul minim de interes, alfa,
  puterea, abaterea estimată și mărimea eșantionului pe variantă calculată la declarare; toate DINAINTE, protejate
  de un declanșator. Regula de oprire e cu eșantion fix: verdictul se calculează automat doar când ambele variante
  au atins mărimea declarată (fără „trasul cu ochiul”), sau `neconcludent` la termen. `tenant_id` gol = test de
  agenție (de exemplu, un prompt); cu client, doar clientul îl vede (RLS).
- `teste_ab_observatii`: o valoare pe unitate (cheie unică pe test), pe variantă.
- `promovari.test_ab_id`: testul formal cu care se măsoară producția unei promovări față de grupul de control.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE teste_ab (
            id uuid PRIMARY KEY,
            tenant_id uuid REFERENCES clienti (id),
            ipoteza text NOT NULL CHECK (length(ipoteza) BETWEEN 10 AND 400),
            obiect text NOT NULL CHECK (length(obiect) BETWEEN 3 AND 120),
            varianta_a text NOT NULL CHECK (length(varianta_a) BETWEEN 1 AND 120),
            varianta_b text NOT NULL CHECK (length(varianta_b) BETWEEN 1 AND 120),
            indicator text NOT NULL CHECK (length(indicator) BETWEEN 3 AND 60),
            efect_minim real NOT NULL CHECK (efect_minim > 0),
            alfa real NOT NULL CHECK (alfa > 0 AND alfa <= 0.2),
            putere real NOT NULL CHECK (putere >= 0.5 AND putere < 1),
            abatere_estimata real NOT NULL CHECK (abatere_estimata > 0),
            n_pe_varianta integer NOT NULL CHECK (n_pe_varianta BETWEEN 2 AND 1000000),
            durata_maxima_zile integer NOT NULL CHECK (durata_maxima_zile BETWEEN 1 AND 365),
            stare text NOT NULL DEFAULT 'in_curs' CHECK (stare IN ('in_curs', 'incheiat')),
            verdict text CHECK (verdict IN ('castiga_a', 'castiga_b', 'fara_diferenta', 'neconcludent')),
            rezultat jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(rezultat) = 'object'),
            declarat_la timestamptz NOT NULL DEFAULT now(),
            incheiat_la timestamptz,
            CHECK (varianta_a <> varianta_b),
            CHECK ((stare = 'incheiat') = (verdict IS NOT NULL)),
            CHECK ((stare = 'in_curs') = (incheiat_la IS NULL))
        )"""
    )
    op.execute(
        """CREATE FUNCTION teste_ab_protejeaza() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (NEW.tenant_id, NEW.ipoteza, NEW.obiect, NEW.varianta_a, NEW.varianta_b, NEW.indicator,
                NEW.efect_minim, NEW.alfa, NEW.putere, NEW.abatere_estimata, NEW.n_pe_varianta,
                NEW.durata_maxima_zile, NEW.declarat_la)
               IS DISTINCT FROM
               (OLD.tenant_id, OLD.ipoteza, OLD.obiect, OLD.varianta_a, OLD.varianta_b, OLD.indicator,
                OLD.efect_minim, OLD.alfa, OLD.putere, OLD.abatere_estimata, OLD.n_pe_varianta,
                OLD.durata_maxima_zile, OLD.declarat_la) THEN
                RAISE EXCEPTION 'ce s-a declarat înaintea testului nu se mai schimbă' USING ERRCODE = '23514';
            END IF;
            IF OLD.stare <> 'in_curs' THEN
                RAISE EXCEPTION 'un test încheiat nu se mai schimbă' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER teste_ab_protejat BEFORE UPDATE ON teste_ab FOR EACH ROW EXECUTE FUNCTION teste_ab_protejeaza()"
    )
    activeaza_rls_tenant(op.execute, "teste_ab")
    op.execute(
        """CREATE TABLE teste_ab_observatii (
            id uuid PRIMARY KEY,
            tenant_id uuid REFERENCES clienti (id),
            test_id uuid NOT NULL REFERENCES teste_ab (id),
            varianta text NOT NULL CHECK (varianta IN ('a', 'b')),
            cheie text NOT NULL CHECK (length(cheie) BETWEEN 1 AND 100),
            valoare double precision NOT NULL,
            la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (test_id, cheie)
        )"""
    )
    activeaza_rls_tenant(op.execute, "teste_ab_observatii", drepturi="SELECT, INSERT")
    op.execute("ALTER TABLE promovari ADD COLUMN test_ab_id uuid REFERENCES teste_ab (id)")


def downgrade() -> None:
    op.execute("ALTER TABLE promovari DROP COLUMN test_ab_id")
    op.execute("DROP TABLE teste_ab_observatii")
    op.execute("DROP TABLE teste_ab")
    op.execute("DROP FUNCTION teste_ab_protejeaza()")
