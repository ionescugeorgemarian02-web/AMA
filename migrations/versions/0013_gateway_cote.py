"""Gateway de modele: contoarele de cotă și blocajele (F3.3, docs/08 §8.4)

Revizia: 0013
Anterioara: 0012

- `gateway_contoare`: câte un contor pe (resursă, fereastră, începutul ferestrei). Resursa este `model:<id>` sau
  `furnizor:<id>` (limite comune contului). Contorul numără cererile și tokenii REZERVAȚI (apoi regularizați cu cei
  reali); rezervarea este o singură instrucțiune atomică sub plafon (vezi `app/gateway/limitator.py`).
- `gateway_blocaje`: resursa nu se folosește până la `pana_la` (după un 429 sau antete care spun „epuizat”).
- Ambele sunt la nivel de agenție (nu țin date de client): citite din orice context cu identitate, scrise de scopul
  de agenție (gateway-ul deschide sesiuni de agenție pentru ele). Fără `tenant_id`.
- OpenRouter aplică limita pe cont, nu pe model: antetele lui corectează contorul contului (`antete_cheie`).
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"
CITIRE = (
    "((SELECT ama_agency()) OR (SELECT ama_tenant_id()) IS NOT NULL OR (SELECT ama_user_id()) IS NOT NULL)"
)


def _politici(tabel: str) -> None:
    activeaza_rls(op.execute, tabel)
    op.execute(f"CREATE POLICY {tabel}_citire ON {tabel} FOR SELECT USING ({CITIRE})")
    op.execute(f"CREATE POLICY {tabel}_adaugare ON {tabel} FOR INSERT WITH CHECK ({AGENTIE})")
    op.execute(
        f"CREATE POLICY {tabel}_schimbare ON {tabel} FOR UPDATE USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute(f"CREATE POLICY {tabel}_stergere ON {tabel} FOR DELETE USING ({AGENTIE})")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tabel} TO ama_app")


def upgrade() -> None:
    op.execute(
        """CREATE TABLE gateway_contoare (
            cheie text NOT NULL CHECK (cheie ~ '^(model|furnizor):[0-9a-f-]{36}$'),
            fereastra text NOT NULL CHECK (fereastra IN ('minut', 'zi')),
            inceput timestamptz NOT NULL,
            cereri integer NOT NULL DEFAULT 0 CHECK (cereri >= 0),
            tokeni bigint NOT NULL DEFAULT 0 CHECK (tokeni >= 0),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (cheie, fereastra, inceput)
        )"""
    )
    op.execute("CREATE INDEX gateway_contoare_vechime ON gateway_contoare (inceput)")
    _politici("gateway_contoare")
    op.execute(
        """CREATE TABLE gateway_blocaje (
            cheie text PRIMARY KEY CHECK (cheie ~ '^(model|furnizor):[0-9a-f-]{36}$'),
            pana_la timestamptz NOT NULL,
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 200),
            actualizat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    _politici("gateway_blocaje")
    # Limita OpenRouter e pe cont: antetele lui se aplică contului, nu unui model (idempotent cu sămânța).
    op.execute("SELECT set_config('app.agency', '1', true)")  # RLS e forțat și pentru proprietarul migrării
    op.execute(
        """UPDATE gateway_furnizori SET parametri = parametri || '{"antete_cheie": "furnizor"}'::jsonb
           WHERE cod = 'openrouter'"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE gateway_blocaje")
    op.execute("DROP TABLE gateway_contoare")
    op.execute("SELECT set_config('app.agency', '1', true)")
    op.execute("UPDATE gateway_furnizori SET parametri = parametri - 'antete_cheie' WHERE cod = 'openrouter'")
