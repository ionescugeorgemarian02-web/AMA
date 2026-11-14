"""Legarea rezultatelor de etichete: hook, format, slot, unghi (F10.3, K2, docs/11 §11.4, docs/13 §13.4)

Revizia: 0059
Anterioara: 0058

- `etichete_postari`: un rând pe postare publicată (livrabil + canal), cu etichetele ei (tiparul hook-ului
  ales, formatul, pilonul și unghiul din calendar, ziua și ora locală a publicării) și recompensa citită
  la 72 de ore (11.4). `recompensa_tip` spune ce fel de recompensă e (nu se compară tipuri diferite);
  `recompensa_interval` spune din ce citire vine (72 de ore, sau prima citire reușită de după, dacă cea de
  la 72 de ore lipsește).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE etichete_postari (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            canal text NOT NULL CHECK (canal ~ '^[a-z][a-z0-9_]{1,39}$'),
            publicat_la timestamptz NOT NULL,
            tipar_hook text NOT NULL DEFAULT '' CHECK (tipar_hook ~ '^[a-z_]{0,30}$'),
            format text NOT NULL CHECK (format ~ '^[a-z][a-z0-9_]{1,49}$'),
            pilon text NOT NULL DEFAULT '' CHECK (length(pilon) <= 80),
            unghi text NOT NULL DEFAULT '' CHECK (length(unghi) <= 300),
            zi_saptamana smallint NOT NULL CHECK (zi_saptamana BETWEEN 1 AND 7),
            ora smallint NOT NULL CHECK (ora BETWEEN 0 AND 23),
            recompensa double precision CHECK (recompensa >= 0),
            recompensa_tip text CHECK (recompensa_tip IN ('interactiuni_pe_afisari', 'retentie_medie')),
            recompensa_interval text CHECK (recompensa_interval IN ('72h', '7z', '28z')),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT etichete_postari_unic UNIQUE (tenant_id, livrabil_id, canal),
            CONSTRAINT etichete_postari_recompensa_intreaga CHECK (
                (recompensa IS NULL) = (recompensa_tip IS NULL) AND (recompensa IS NULL) = (recompensa_interval IS NULL)
            )
        )"""
    )
    op.execute("CREATE INDEX etichete_postari_hook ON etichete_postari (tenant_id, tipar_hook)")
    activeaza_rls_tenant(op.execute, "etichete_postari")


def downgrade() -> None:
    op.execute("DROP TABLE etichete_postari")
