"""Validare: calibrarea judecătorilor (F5.8, G14, docs/09 §9.6)

Revizia: 0032
Anterioara: 0031

- `calibrare_etichete`: verdictele V3 / V4 alese în eșantionul săptămânal pentru etichetare umană („corect” /
„greșit” +
  motiv). Pe client (verdictul și textul sunt ale clientului), RLS. Rândul are clientul verdictului
  (declanșator), iar o
  etichetă pusă nu se mai schimbă.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE calibrare_etichete (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            verdict_id uuid NOT NULL UNIQUE REFERENCES validari_verdicte (id),
            judecator text NOT NULL CHECK (judecator ~ '^G[0-9]{1,2}@V[34]$'),
            versiune text NOT NULL CHECK (length(versiune) BETWEEN 1 AND 300),
            judecator_esec boolean NOT NULL,
            saptamana text NOT NULL CHECK (saptamana ~ '^[0-9]{4}-W[0-9]{2}$'),
            stare text NOT NULL DEFAULT 'de_etichetat' CHECK (stare IN ('de_etichetat', 'etichetat')),
            eticheta text CHECK (eticheta IN ('corect', 'gresit')),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 500),
            etichetat_de uuid REFERENCES utilizatori (id),
            etichetat_la timestamptz,
            creat_la timestamptz NOT NULL DEFAULT now(),
            CHECK ((stare = 'etichetat') = (eticheta IS NOT NULL AND etichetat_la IS NOT NULL)),
            CHECK (eticheta IS DISTINCT FROM 'gresit' OR length(motiv) >= 3)
        )"""
    )
    op.execute("CREATE INDEX calibrare_etichete_stare ON calibrare_etichete (stare, creat_la)")
    op.execute("CREATE INDEX calibrare_etichete_judecator ON calibrare_etichete (judecator, stare)")
    activeaza_rls_tenant(op.execute, "calibrare_etichete", drepturi="SELECT, INSERT, UPDATE")
    op.execute(
        """CREATE FUNCTION calibrare_etichete_verifica() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' AND NEW.tenant_id IS DISTINCT FROM
                    (SELECT tenant_id FROM validari_verdicte WHERE id = NEW.verdict_id) THEN
                RAISE EXCEPTION 'eticheta trebuie să aibă clientul verdictului' USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'UPDATE' AND (OLD.stare = 'etichetat'
                    OR (NEW.tenant_id, NEW.verdict_id, NEW.judecator, NEW.versiune,
                    NEW.judecator_esec, NEW.saptamana)
                    IS DISTINCT FROM (OLD.tenant_id, OLD.verdict_id, OLD.judecator,
                    OLD.versiune, OLD.judecator_esec,
                                      OLD.saptamana)) THEN
                RAISE EXCEPTION 'o etichetă pusă nu se schimbă' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER calibrare_etichete_verifica BEFORE INSERT OR UPDATE ON calibrare_etichete "
        "FOR EACH ROW EXECUTE FUNCTION calibrare_etichete_verifica()"
    )


def downgrade() -> None:
    op.execute("DROP TABLE calibrare_etichete")
    op.execute("DROP FUNCTION calibrare_etichete_verifica()")
