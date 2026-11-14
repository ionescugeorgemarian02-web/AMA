"""Colectorul de metrici: citirile pe intervale ale postărilor publicate (F10.1, K1, docs/07 §7.2)

Revizia: 0057
Anterioara: 0056

- `metrici_postari`: un rând pe (livrabil, canal, interval). `interval` este unul dintre momentele din 7.2
  (1 oră, 24 de ore, 72 de ore, 7 zile, 28 de zile de la publicare). `stare`: `citit` (cifrele există),
  `ratat` (intervalul a trecut fără citire: colectorul era oprit sau platforma nu a răspuns la timp),
  `indisponibil` (platforma a refuzat: postare ștearsă, ciornă nepublicată). `sursa`: `api` sau `manual`
  (cifre introduse de om din exportul platformei, pentru canalele asistate).
- `valori` ține doar cifrele pe care platforma le-a dat (chei din `contract.CHEI_METRICI`), cumulate de la
  publicare; `intarziere_s` spune cu cât a întârziat citirea față de momentul intervalului.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE metrici_postari (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            canal text NOT NULL CHECK (canal ~ '^[a-z][a-z0-9_]{1,39}$'),
            id_extern text NOT NULL DEFAULT '' CHECK (length(id_extern) <= 300),
            interval text NOT NULL CHECK (interval IN ('1h', '24h', '72h', '7z', '28z')),
            stare text NOT NULL CHECK (stare IN ('citit', 'ratat', 'indisponibil')),
            sursa text NOT NULL DEFAULT 'api' CHECK (sursa IN ('api', 'manual')),
            valori jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(valori) = 'object'),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 300),
            publicat_la timestamptz NOT NULL,
            citit_la timestamptz NOT NULL DEFAULT now(),
            intarziere_s integer NOT NULL DEFAULT 0 CHECK (intarziere_s >= 0),
            introdus_de uuid REFERENCES utilizatori (id),
            CONSTRAINT metrici_postari_unic UNIQUE (tenant_id, livrabil_id, canal, interval),
            CONSTRAINT metrici_postari_citit_are_valori CHECK (stare = 'citit' OR valori = '{}'::jsonb),
            CONSTRAINT metrici_postari_manual_are_om CHECK ((sursa = 'manual') = (introdus_de IS NOT NULL))
        )"""
    )
    op.execute("CREATE INDEX metrici_postari_livrabil ON metrici_postari (livrabil_id, canal)")
    op.execute("CREATE INDEX metrici_postari_citit_la ON metrici_postari (tenant_id, citit_la)")
    activeaza_rls_tenant(op.execute, "metrici_postari")


def downgrade() -> None:
    op.execute("DROP TABLE metrici_postari")
