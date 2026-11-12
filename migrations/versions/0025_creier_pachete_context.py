"""Creierul: pachetele de context (F4.7, docs/10 §10.3, docs/20 §20.3)

Revizia: 0025
Anterioara: 0024

- `pachete_context`: ce a primit o sarcină din Creier — referințe (identificator + versiune) și un instantaneu compact al
  fiecărui element, bugetul, ce s-a tăiat și ce lipsea — legat de livrabil, ca urma lui să arate „din ce fapte” a ieșit.
  Doar adăugări (nu se modifică și nu se șterge: ama_app are doar SELECT și INSERT), cu RLS pe client; un declanșator
  refuză un pachet legat de livrabilul altui client.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE pachete_context (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid REFERENCES livrabile (id),
            tip_sarcina text NOT NULL CHECK (tip_sarcina ~ '^[a-z][a-z0-9_.]{1,60}$'),
            canal text CHECK (canal ~ '^[a-z][a-z0-9_]{1,30}$'),
            intrebare text NOT NULL CHECK (length(intrebare) <= 2000),
            la timestamptz NOT NULL,
            buget_tokeni integer NOT NULL CHECK (buget_tokeni > 0),
            tokeni_folositi integer NOT NULL CHECK (tokeni_folositi >= 0),
            depasit boolean NOT NULL DEFAULT false,
            amprenta text NOT NULL CHECK (amprenta ~ '^[0-9a-f]{64}$'),
            continut jsonb NOT NULL CHECK (jsonb_typeof(continut) = 'object'),
            lipsuri jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(lipsuri) = 'array'),
            taiate jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(taiate) = 'array'),
            creat_la timestamptz NOT NULL DEFAULT now(),
            creat_de uuid REFERENCES utilizatori (id)
        )"""
    )
    op.execute("CREATE INDEX pachete_context_livrabil ON pachete_context (livrabil_id, creat_la DESC)")
    op.execute("CREATE INDEX pachete_context_client ON pachete_context (tenant_id, creat_la DESC)")
    op.execute(
        """CREATE FUNCTION pachete_context_la_inserare() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.livrabil_id IS NOT NULL
               AND NEW.tenant_id IS DISTINCT FROM (SELECT tenant_id FROM livrabile WHERE id = NEW.livrabil_id) THEN
                RAISE EXCEPTION 'pachetul trebuie să aibă clientul livrabilului' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER pachete_context_la_inserare BEFORE INSERT ON pachete_context "
        "FOR EACH ROW EXECUTE FUNCTION pachete_context_la_inserare()"
    )
    activeaza_rls_tenant(op.execute, "pachete_context", drepturi="SELECT, INSERT")


def downgrade() -> None:
    op.execute("DROP TABLE pachete_context")  # declanșatorul pleacă odată cu tabelul
    op.execute("DROP FUNCTION pachete_context_la_inserare()")
