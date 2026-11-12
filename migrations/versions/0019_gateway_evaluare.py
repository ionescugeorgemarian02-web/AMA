"""Gateway de modele: testul comparativ pe română (F3.6, docs/08 §8.10)

Revizia: 0019
Anterioara: 0018

- `gateway_evaluari_rulari`: o rulare a setului de sarcini pe UN model (cine, când, amprenta setului, starea, scorul agregat pe
  profil). Istoricul se păstrează; nu se șterge.
- `gateway_evaluari_rezultate`: rezultatul fiecărei sarcini (scor automat, criteriile, răspunsul modelului, nota umană 1–5 cu cine
  și când). Sarcinile sunt sintetice (`evaluare/sarcini/`), fără date de client: tabelele sunt la nivel de agenție (citite din
  orice context cu identitate, scrise de scopul de agenție), ca registrul de modele.
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0019"
down_revision = "0018"
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
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {tabel} TO ama_app")


def upgrade() -> None:
    op.execute(
        """CREATE TABLE gateway_evaluari_rulari (
            id uuid PRIMARY KEY,
            model_id uuid NOT NULL REFERENCES gateway_modele (id),
            model_cod text NOT NULL CHECK (length(model_cod) BETWEEN 3 AND 250),
            set_amprenta text NOT NULL CHECK (set_amprenta ~ '^[0-9a-f]{64}$'),
            profiluri text[] NOT NULL,
            stare text NOT NULL DEFAULT 'in_curs' CHECK (stare IN ('in_curs', 'amanata', 'terminata', 'esuata')),
            amanata_pana_la timestamptz,
            sarcini_total integer NOT NULL CHECK (sarcini_total >= 0),
            sarcini_facute integer NOT NULL DEFAULT 0 CHECK (sarcini_facute >= 0),
            scor jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(scor) = 'object'),
            in_registru boolean NOT NULL DEFAULT false,
            pornita_la timestamptz NOT NULL DEFAULT now(),
            terminata_la timestamptz,
            pornita_de uuid REFERENCES utilizatori (id)
        )"""
    )
    op.execute(
        "CREATE INDEX gateway_evaluari_rulari_model ON gateway_evaluari_rulari (model_id, pornita_la DESC)"
    )
    _politici("gateway_evaluari_rulari")
    op.execute(
        """CREATE TABLE gateway_evaluari_rezultate (
            rulare_id uuid NOT NULL REFERENCES gateway_evaluari_rulari (id),
            sarcina_id text NOT NULL CHECK (sarcina_id ~ '^[a-z]+-[0-9]{2,3}$'),
            profil text NOT NULL CHECK (profil ~ '^[a-z][a-z0-9_]{1,40}$'),
            stare text NOT NULL CHECK (stare IN ('ok', 'invalid', 'esec')),
            scor_auto numeric(5, 4) NOT NULL CHECK (scor_auto BETWEEN 0 AND 1),
            detalii jsonb NOT NULL DEFAULT '{}'::jsonb,
            raspuns jsonb,
            cod_eroare text NOT NULL DEFAULT '' CHECK (length(cod_eroare) <= 100),
            tokeni integer NOT NULL DEFAULT 0 CHECK (tokeni >= 0),
            durata_ms integer NOT NULL DEFAULT 0 CHECK (durata_ms >= 0),
            nota_umana smallint CHECK (nota_umana BETWEEN 1 AND 5),
            nota_de uuid REFERENCES utilizatori (id),
            nota_la timestamptz,
            creat_la timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (rulare_id, sarcina_id)
        )"""
    )
    _politici("gateway_evaluari_rezultate")


def downgrade() -> None:
    op.execute("DROP TABLE gateway_evaluari_rezultate")
    op.execute("DROP TABLE gateway_evaluari_rulari")
