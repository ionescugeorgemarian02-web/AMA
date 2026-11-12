"""Nivelurile de autonomie (F2.10, 7.4, ADR-12)

Revizia: 0010
Anterioara: 0009

- `autonomie_niveluri`: nivelul L0–L4 pe client și pe clasă de acțiune (5 clase). Fără rând = implicit L1.
- `autonomie_istoric`: doar-adăugare; fiecare schimbare (de proprietar sau retrogradare automată la incident critic)
  cu cine, când, de la ce nivel la care și de ce. O „setare” cere un om (`utilizator_id`); o retrogradare vine de la sistem.
  Din istoric se poate calcula mai târziu criteriul de promovare (zero incidente critice pe ultimele 30 de livrabile);
  promovarea automată L1 → L2 NU se construiește acum.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

CLASE = ("publicare_continut", "raspuns_inbox", "schimbare_reclame", "schimbare_strategie", "cheltuiala")


def _lista(valori: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in valori)


def upgrade() -> None:
    op.execute(
        f"""CREATE TABLE autonomie_niveluri (
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            clasa text NOT NULL CHECK (clasa IN ({_lista(CLASE)})),
            nivel smallint NOT NULL CHECK (nivel BETWEEN 0 AND 4),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 300),
            schimbat_de uuid REFERENCES utilizatori (id),
            schimbat_la timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, clasa)
        )"""
    )
    activeaza_rls_tenant(op.execute, "autonomie_niveluri", drepturi="SELECT, INSERT, UPDATE")

    op.execute(
        f"""CREATE TABLE autonomie_istoric (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            clasa text NOT NULL CHECK (clasa IN ({_lista(CLASE)})),
            de_la smallint NOT NULL CHECK (de_la BETWEEN 0 AND 4),
            la smallint NOT NULL CHECK (la BETWEEN 0 AND 4),
            tip text NOT NULL CHECK (tip IN ('setare', 'retrogradare')),
            utilizator_id uuid REFERENCES utilizatori (id),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 300),
            referinta text NOT NULL DEFAULT '' CHECK (length(referinta) <= 120),
            creat_la timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK (de_la <> la),
            CHECK (tip <> 'setare' OR utilizator_id IS NOT NULL),
            CHECK (tip <> 'retrogradare' OR la = de_la - 1)
        )"""
    )
    op.execute("CREATE INDEX autonomie_istoric_client ON autonomie_istoric (tenant_id, creat_la DESC)")
    op.execute(
        "CREATE TRIGGER autonomie_istoric_fara_modificari BEFORE UPDATE OR DELETE ON autonomie_istoric "
        "FOR EACH ROW EXECUTE FUNCTION ama_jurnal_doar_adaugare()"
    )
    op.execute(
        "CREATE TRIGGER autonomie_istoric_fara_golire BEFORE TRUNCATE ON autonomie_istoric "
        "FOR EACH STATEMENT EXECUTE FUNCTION ama_jurnal_doar_adaugare()"
    )
    activeaza_rls_tenant(op.execute, "autonomie_istoric", drepturi="SELECT, INSERT")


def downgrade() -> None:
    op.execute("DROP TABLE autonomie_istoric")
    op.execute("DROP TABLE autonomie_niveluri")
