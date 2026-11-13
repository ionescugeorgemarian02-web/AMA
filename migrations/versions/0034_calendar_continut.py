"""Conținut: calendarul lunar al strategului de conținut (F6.1, D3, docs/13 §13.2, docs/05)

Revizia: 0034
Anterioara: 0033

- `calendare`: propunerea strategului (piloni, formate pe canal, idei) legată de versiunea APROBATĂ a strategiei pe 90 de
  zile, pe o fereastră de zile; stările `propus` → `aprobat` / `respins` / `inlocuit`. Decizia o ia un om (`decis_de`).
- `calendar_intrari`: sloturile calendarului (dată și oră UTC, canal, tip de livrabil, pilon, subiect, unghi). La aprobare,
  fiecare slot primește livrabilul lui (`planificat`); altfel rândul nu se mai schimbă.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE calendare (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            inceput date NOT NULL,
            zile integer NOT NULL CHECK (zile BETWEEN 7 AND 62),
            strategie_intrare_id uuid NOT NULL,
            strategie_versiune integer NOT NULL CHECK (strategie_versiune >= 1),
            propunere jsonb NOT NULL,
            pachet_id uuid,
            model text,
            stare text NOT NULL DEFAULT 'propus' CHECK (stare IN ('propus', 'aprobat', 'respins', 'inlocuit')),
            motiv text CHECK (motiv IS NULL OR length(motiv) <= 300),
            decis_de uuid REFERENCES utilizatori (id),
            decis_la timestamptz,
            creat_de uuid REFERENCES utilizatori (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            CHECK (stare NOT IN ('aprobat', 'respins') OR (decis_de IS NOT NULL AND decis_la IS NOT NULL)),
            CHECK (stare <> 'respins' OR length(coalesce(motiv, '')) >= 3)
        )"""
    )
    op.execute("CREATE INDEX calendare_client ON calendare (tenant_id, creat_la DESC)")
    op.execute(
        """CREATE TABLE calendar_intrari (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            calendar_id uuid NOT NULL REFERENCES calendare (id),
            nr integer NOT NULL CHECK (nr >= 1),
            slot_la timestamptz NOT NULL,
            canal text NOT NULL CHECK (canal ~ '^[a-z][a-z0-9_]{1,39}$'),
            tip text NOT NULL CHECK (tip ~ '^[a-z][a-z0-9_]{1,39}$'),
            pilon text NOT NULL CHECK (length(pilon) BETWEEN 2 AND 80),
            subiect text NOT NULL CHECK (length(subiect) BETWEEN 5 AND 300),
            unghi text NOT NULL DEFAULT '' CHECK (length(unghi) <= 300),
            livrabil_id uuid UNIQUE REFERENCES livrabile (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (calendar_id, nr)
        )"""
    )
    op.execute("CREATE INDEX calendar_intrari_slot ON calendar_intrari (tenant_id, slot_la)")
    op.execute(
        """CREATE FUNCTION calendar_intrari_protejeaza() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.tenant_id IS DISTINCT FROM (SELECT tenant_id FROM calendare WHERE id = NEW.calendar_id) THEN
                RAISE EXCEPTION 'slotul trebuie să aibă clientul calendarului' USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'UPDATE' AND (
                (NEW.calendar_id, NEW.nr, NEW.slot_la, NEW.canal, NEW.tip, NEW.pilon, NEW.subiect, NEW.unghi, NEW.tenant_id)
                IS DISTINCT FROM
                (OLD.calendar_id, OLD.nr, OLD.slot_la, OLD.canal, OLD.tip, OLD.pilon, OLD.subiect, OLD.unghi, OLD.tenant_id)
                OR (OLD.livrabil_id IS NOT NULL AND NEW.livrabil_id IS DISTINCT FROM OLD.livrabil_id)
            ) THEN
                RAISE EXCEPTION 'slotul nu se schimbă; primește o singură dată livrabilul' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER calendar_intrari_protejat BEFORE INSERT OR UPDATE ON calendar_intrari "
        "FOR EACH ROW EXECUTE FUNCTION calendar_intrari_protejeaza()"
    )
    activeaza_rls_tenant(op.execute, "calendare", drepturi="SELECT, INSERT, UPDATE")
    activeaza_rls_tenant(op.execute, "calendar_intrari", drepturi="SELECT, INSERT, UPDATE")


def downgrade() -> None:
    op.execute("DROP TABLE calendar_intrari")
    op.execute("DROP FUNCTION calendar_intrari_protejeaza()")
    op.execute("DROP TABLE calendare")
