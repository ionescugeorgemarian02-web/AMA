"""Publicarea asistată: pachetul pe telefon și linkul lipit de om (F6.6, H1, docs/15 §15.2, §15.4, §15.6)

Revizia: 0038
Anterioara: 0037

- `publicari_asistate`: pachetul complet al unei versiuni APROBATE (text final cu hashtag-uri, canal, ora recomandată,
  dezvăluirea AI și pașii obligatorii, cheia de idempotență client:livrabil:canal:versiune:tip), apoi linkul postării
  lipit de omul care a publicat. Platforma nu publică nimic în modul asistat: publică omul, din telefon.
  Stări: `pregatit` → `publicat` (cu link) / `anulat`. Pachetul nu se schimbă; linkul se pune o singură dată.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE publicari_asistate (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            versiune integer NOT NULL CHECK (versiune >= 1),
            canal text NOT NULL CHECK (canal ~ '^[a-z][a-z0-9_]{1,39}$'),
            cheie text NOT NULL UNIQUE,
            pachet jsonb NOT NULL,
            stare text NOT NULL DEFAULT 'pregatit' CHECK (stare IN ('pregatit', 'publicat', 'anulat')),
            link text CHECK (link IS NULL OR (link ~ '^https://' AND length(link) <= 500)),
            publicat_de uuid REFERENCES utilizatori (id),
            publicat_la timestamptz,
            creat_la timestamptz NOT NULL DEFAULT now(),
            CHECK (stare <> 'publicat' OR (link IS NOT NULL AND publicat_de IS NOT NULL AND publicat_la IS NOT NULL))
        )"""
    )
    op.execute(
        "CREATE INDEX publicari_asistate_pregatite ON publicari_asistate (tenant_id, creat_la) WHERE stare = 'pregatit'"
    )
    op.execute(
        """CREATE FUNCTION publicari_asistate_protejeaza() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.tenant_id IS DISTINCT FROM (SELECT tenant_id FROM livrabile WHERE id = NEW.livrabil_id) THEN
                RAISE EXCEPTION 'pachetul trebuie să aibă clientul livrabilului' USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'UPDATE' AND (
                (NEW.livrabil_id, NEW.versiune, NEW.canal, NEW.cheie, NEW.pachet, NEW.tenant_id)
                IS DISTINCT FROM (OLD.livrabil_id, OLD.versiune, OLD.canal, OLD.cheie, OLD.pachet, OLD.tenant_id)
                OR OLD.stare <> 'pregatit'
            ) THEN
                RAISE EXCEPTION 'pachetul nu se schimbă; linkul se pune o singură dată' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER publicari_asistate_protejat BEFORE INSERT OR UPDATE ON publicari_asistate "
        "FOR EACH ROW EXECUTE FUNCTION publicari_asistate_protejeaza()"
    )
    activeaza_rls_tenant(op.execute, "publicari_asistate", drepturi="SELECT, INSERT, UPDATE")


def downgrade() -> None:
    op.execute("DROP TABLE publicari_asistate")
    op.execute("DROP FUNCTION publicari_asistate_protejeaza()")
