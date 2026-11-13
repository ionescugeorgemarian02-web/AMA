"""Validare: conținutul livrabilului, rulările cascadei și verdictele (F5.1, docs/09 §9.2)

Revizia: 0028
Anterioara: 0027

- `livrabile_continut`: o versiune de conținut (text + câmpuri pe canal + active declarate), legată de
  `livrabile.versiune`. Acoperire provizorie până la F6. Doar adăugare.
- `validari_rulari`: o trecere a cascadei peste o versiune de livrabil (runda de reparație, rezultatul, punctele de
  avertisment, instrucțiunea unificată). Doar adăugare.
- `validari_verdicte`: verdictul fiecărui validator (identitate + versiune, treaptă, rezultat, severitate, scor, dovezi,
  instrucțiune, cost). Doar adăugare. Pe client, cu RLS.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

TABELE = ("livrabile_continut", "validari_rulari", "validari_verdicte")


def _doar_adaugare(tabel: str) -> None:
    op.execute(
        f"CREATE TRIGGER {tabel}_fara_modificari BEFORE UPDATE OR DELETE ON {tabel} "
        "FOR EACH ROW EXECUTE FUNCTION ama_jurnal_doar_adaugare()"
    )
    op.execute(
        f"CREATE TRIGGER {tabel}_fara_golire BEFORE TRUNCATE ON {tabel} "
        "FOR EACH STATEMENT EXECUTE FUNCTION ama_jurnal_doar_adaugare()"
    )


def upgrade() -> None:
    op.execute(
        """CREATE TABLE livrabile_continut (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            versiune integer NOT NULL CHECK (versiune >= 1),
            text text NOT NULL CHECK (length(text) <= 200000),
            campuri jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(campuri) = 'object'),
            active jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(active) = 'array'),
            autor text NOT NULL CHECK (length(autor) BETWEEN 1 AND 60),
            model_autor text,
            amprenta text NOT NULL CHECK (amprenta ~ '^[0-9a-f]{64}$'),
            creat_la timestamptz NOT NULL DEFAULT now(),
            creat_de uuid REFERENCES utilizatori (id),
            UNIQUE (livrabil_id, versiune)
        )"""
    )
    op.execute(
        """CREATE FUNCTION livrabile_continut_la_inserare() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.tenant_id IS DISTINCT FROM (SELECT tenant_id FROM livrabile WHERE id = NEW.livrabil_id) THEN
                RAISE EXCEPTION 'conținutul trebuie să aibă clientul livrabilului' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER livrabile_continut_client BEFORE INSERT ON livrabile_continut "
        "FOR EACH ROW EXECUTE FUNCTION livrabile_continut_la_inserare()"
    )
    op.execute(
        """CREATE TABLE validari_rulari (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            versiune integer NOT NULL CHECK (versiune >= 1),
            runda integer NOT NULL CHECK (runda >= 0),
            decizie text NOT NULL CHECK (decizie IN ('trece', 'reparatie', 'carantina', 'intrebare')),
            cere_om boolean NOT NULL DEFAULT false,
            puncte integer NOT NULL CHECK (puncte >= 0),
            prag integer NOT NULL CHECK (prag >= 0),
            oprit_la_treapta text,
            instructiune text NOT NULL DEFAULT '',
            amprenta text NOT NULL CHECK (amprenta ~ '^[0-9a-f]{64}$'),
            cost jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(cost) = 'object'),
            creat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX validari_rulari_livrabil ON validari_rulari (livrabil_id, creat_la)")
    op.execute(
        """CREATE TABLE validari_verdicte (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            rulare_id uuid NOT NULL REFERENCES validari_rulari (id),
            livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            versiune integer NOT NULL CHECK (versiune >= 1),
            runda integer NOT NULL CHECK (runda >= 0),
            validator text NOT NULL CHECK (validator ~ '^[A-Z][A-Z0-9_]{0,15}$'),
            validator_versiune text NOT NULL CHECK (length(validator_versiune) BETWEEN 1 AND 40),
            treapta text NOT NULL CHECK (treapta IN ('V0', 'V1', 'V2', 'V3', 'V4', 'V5')),
            rezultat text NOT NULL CHECK (rezultat IN ('trece', 'avertisment', 'esec')),
            severitate text CHECK (severitate IN ('minora', 'majora', 'critica')),
            scor double precision NOT NULL CHECK (scor >= 0 AND scor <= 1),
            dovezi jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(dovezi) = 'array'),
            instructiune text NOT NULL DEFAULT '',
            cost jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(cost) = 'object'),
            detalii jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(detalii) = 'object'),
            amprenta text NOT NULL CHECK (amprenta ~ '^[0-9a-f]{64}$'),
            creat_la timestamptz NOT NULL DEFAULT now(),
            CHECK ((rezultat = 'trece') = (severitate IS NULL)),
            CHECK (rezultat <> 'esec' OR severitate IN ('majora', 'critica'))
        )"""
    )
    op.execute(
        "CREATE INDEX validari_verdicte_livrabil ON validari_verdicte (livrabil_id, versiune, creat_la)"
    )
    op.execute(
        "CREATE INDEX validari_verdicte_validator ON validari_verdicte (tenant_id, validator, creat_la DESC)"
    )
    op.execute("CREATE INDEX validari_verdicte_rulare ON validari_verdicte (rulare_id)")
    for t in TABELE:
        _doar_adaugare(t)
        activeaza_rls_tenant(op.execute, t, drepturi="SELECT, INSERT")


def downgrade() -> None:
    op.execute("DROP TABLE validari_verdicte")
    op.execute("DROP TABLE validari_rulari")
    op.execute("DROP TABLE livrabile_continut")
    op.execute("DROP FUNCTION livrabile_continut_la_inserare()")
