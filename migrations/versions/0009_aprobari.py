"""Cererile de aprobare (F2.8, 7.3, 18.3, 19.4)

Revizia: 0009
Anterioara: 0008

`aprobari`: o cerere pentru o VERSIUNE a unui livrabil, adresată unui decident (operator sau client), cu termen,
reamintire și stare (în așteptare / aprobat / respins / expirat / anulat). Reguli impuse în bază:
- cel mult o cerere în așteptare pe livrabil (indice unic parțial);
- o decizie înregistrată nu se mai schimbă (declanșator): nici aprobarea unei cereri expirate, nici reluarea;
- legătura cu versiunea, cu clientul și cu livrabilul este neschimbabilă;
- respingerea cere un motiv; aprobarea și respingerea cer un decident.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

CLASE = ("publicare_continut", "raspuns_inbox", "schimbare_reclame", "schimbare_strategie", "cheltuiala")
MOTIVE = (
    "fapt_gresit",
    "ton_nepotrivit",
    "prea_lung",
    "hook_slab",
    "subiect_nepotrivit",
    "vizual_slab",
    "conformitate",
    "altceva",
)


def _lista(valori: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in valori)


def upgrade() -> None:
    op.execute(
        f"""CREATE TABLE aprobari (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            versiune integer NOT NULL CHECK (versiune >= 1),
            clasa_actiune text NOT NULL CHECK (clasa_actiune IN ({_lista(CLASE)})),
            decident text NOT NULL CHECK (decident IN ('operator', 'client')),
            stare text NOT NULL DEFAULT 'in_asteptare'
                CHECK (stare IN ('in_asteptare', 'aprobat', 'respins', 'expirat', 'anulat')),
            termen_la timestamptz NOT NULL,
            reamintire_la timestamptz NOT NULL,
            reamintit_la timestamptz,
            motiv_cod text CHECK (motiv_cod IS NULL OR motiv_cod IN ({_lista(MOTIVE)})),
            motiv text CHECK (motiv IS NULL OR length(motiv) <= 300),
            decis_de uuid REFERENCES utilizatori (id),
            decis_la timestamptz,
            creat_de uuid REFERENCES utilizatori (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            CHECK ((stare = 'in_asteptare') = (decis_la IS NULL)),
            CHECK ((stare IN ('aprobat', 'respins')) = (decis_de IS NOT NULL)),
            CHECK (stare <> 'respins' OR length(coalesce(motiv, '')) >= 3)
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX aprobari_una_in_asteptare ON aprobari (livrabil_id) WHERE stare = 'in_asteptare'"
    )
    op.execute("CREATE INDEX aprobari_termen ON aprobari (termen_la) WHERE stare = 'in_asteptare'")
    op.execute("CREATE INDEX aprobari_tenant ON aprobari (tenant_id, stare, creat_la DESC)")
    op.execute(
        """CREATE FUNCTION ama_aprobare_garda() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.stare <> 'in_asteptare' THEN
                RAISE EXCEPTION 'o decizie înregistrată nu se mai schimbă (cererea % este %)', OLD.id, OLD.stare
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF NEW.id <> OLD.id OR NEW.tenant_id <> OLD.tenant_id OR NEW.livrabil_id <> OLD.livrabil_id
               OR NEW.versiune <> OLD.versiune OR NEW.decident <> OLD.decident
               OR NEW.clasa_actiune <> OLD.clasa_actiune OR NEW.termen_la <> OLD.termen_la THEN
                RAISE EXCEPTION 'cererea de aprobare este legată de livrabil, versiune și termen'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER aprobari_garda BEFORE UPDATE ON aprobari "
        "FOR EACH ROW EXECUTE FUNCTION ama_aprobare_garda()"
    )
    # fără DELETE: o cerere nu se șterge, se închide
    activeaza_rls_tenant(op.execute, "aprobari", drepturi="SELECT, INSERT, UPDATE")


def downgrade() -> None:
    op.execute("DROP TABLE aprobari")
    op.execute("DROP FUNCTION ama_aprobare_garda()")
