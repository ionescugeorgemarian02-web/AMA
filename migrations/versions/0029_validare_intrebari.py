"""Validare: întrebările către client când lipsește un fapt necesar (F5.3, docs/09 §9.3)

Revizia: 0029
Anterioara: 0028

- `validari_intrebari`: livrabilul se oprește cu o întrebare, nu cu o presupunere. O înregistrare vizibilă: ce fapt lipsește,
  la ce versiune, cine a cerut-o (validatorul), starea (`deschisa` → `raspunsa` / `inchisa`) și răspunsul. Răspunsul nu
  devine fapt: faptul îl propune și îl aprobă un om în Creier, apoi livrabilul se reia. Se modifică doar starea și urmele ei.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE validari_intrebari (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            versiune integer NOT NULL CHECK (versiune >= 1),
            validator text NOT NULL CHECK (validator ~ '^[A-Z][A-Z0-9_]{0,15}$'),
            intrebare text NOT NULL CHECK (length(intrebare) BETWEEN 5 AND 1000),
            tip_fapt text,
            subiect text,
            stare text NOT NULL DEFAULT 'deschisa' CHECK (stare IN ('deschisa', 'raspunsa', 'inchisa')),
            raspuns text CHECK (raspuns IS NULL OR length(raspuns) <= 4000),
            raspuns_de uuid REFERENCES utilizatori (id),
            raspuns_la timestamptz,
            creat_la timestamptz NOT NULL DEFAULT now(),
            CHECK (stare = 'deschisa' OR raspuns_la IS NOT NULL)
        )"""
    )
    op.execute("CREATE INDEX validari_intrebari_livrabil ON validari_intrebari (livrabil_id, creat_la)")
    op.execute(
        "CREATE INDEX validari_intrebari_deschise ON validari_intrebari (tenant_id, creat_la) WHERE stare = 'deschisa'"
    )
    op.execute(
        "CREATE UNIQUE INDEX validari_intrebari_unica ON validari_intrebari (livrabil_id, versiune, intrebare)"
    )
    op.execute(
        """CREATE FUNCTION validari_intrebari_protejeaza() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.tenant_id IS DISTINCT FROM (SELECT tenant_id FROM livrabile WHERE id = NEW.livrabil_id) THEN
                RAISE EXCEPTION 'întrebarea trebuie să aibă clientul livrabilului' USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'UPDATE' AND (NEW.livrabil_id, NEW.versiune, NEW.validator, NEW.intrebare, NEW.tenant_id)
                IS DISTINCT FROM (OLD.livrabil_id, OLD.versiune, OLD.validator, OLD.intrebare, OLD.tenant_id) THEN
                RAISE EXCEPTION 'întrebarea nu se schimbă, doar starea ei' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER validari_intrebari_protejat BEFORE INSERT OR UPDATE ON validari_intrebari "
        "FOR EACH ROW EXECUTE FUNCTION validari_intrebari_protejeaza()"
    )
    activeaza_rls_tenant(op.execute, "validari_intrebari", drepturi="SELECT, INSERT, UPDATE")


def downgrade() -> None:
    op.execute("DROP TABLE validari_intrebari")
    op.execute("DROP FUNCTION validari_intrebari_protejeaza()")
