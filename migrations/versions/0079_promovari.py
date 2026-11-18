"""Învățare: umbra, canarul, promovarea și revenirea unui prompt optimizat (F14.2, docs/11 §11.5 pașii 6–8)

Revizia: 0079
Anterioara: 0078

- `promovari`: drumul unui candidat al optimizatorului: `umbra` → `canar` (10%) → `productie` (90%, cu 10% grup
  de control pe campionul vechi) → `promovat`; sau `respins` / `revenit`. O singură promovare în curs pe
  componentă (index unic parțial). `istoric` ține fiecare trecere, cu motiv și moment.
- `promovari_observatii`: scorurile livrabilelor (doar cifre: scor, conformitate, o cheie opacă), pe etapă și pe
  grup (`campion` / `candidat`), cu `umbra` pentru producțiile care nu se folosesc.
  Ambele la nivel de agenție (D-020), fără conținut de client.
"""

from alembic import op

from app.db.rls import activeaza_rls

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None

TABELE = ("promovari", "promovari_observatii")


def upgrade() -> None:
    op.execute(
        """CREATE TABLE promovari (
            id uuid PRIMARY KEY,
            optimizare_id uuid NOT NULL UNIQUE REFERENCES optimizari (id),
            componenta text NOT NULL CHECK (length(componenta) BETWEEN 1 AND 100),
            campion_versiune integer NOT NULL CHECK (campion_versiune >= 1),
            candidat_versiune integer NOT NULL CHECK (candidat_versiune > campion_versiune),
            revenire_versiune integer CHECK (revenire_versiune > candidat_versiune),
            etapa text NOT NULL DEFAULT 'umbra'
                CHECK (etapa IN ('umbra', 'canar', 'productie', 'promovat', 'respins', 'revenit')),
            procent_candidat integer NOT NULL DEFAULT 0 CHECK (procent_candidat BETWEEN 0 AND 100),
            istoric jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(istoric) = 'array'),
            castig jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(castig) = 'object'),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 300),
            creat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            promovat_la timestamptz,
            incheiat_la timestamptz,
            CHECK ((etapa IN ('umbra', 'canar', 'productie')) = (incheiat_la IS NULL))
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX promovari_una_in_curs ON promovari (componenta) "
        "WHERE etapa IN ('umbra', 'canar', 'productie')"
    )
    op.execute(
        """CREATE TABLE promovari_observatii (
            id uuid PRIMARY KEY,
            promovare_id uuid NOT NULL REFERENCES promovari (id),
            etapa text NOT NULL CHECK (etapa IN ('umbra', 'canar', 'productie')),
            grup text NOT NULL CHECK (grup IN ('campion', 'candidat')),
            umbra boolean NOT NULL DEFAULT false,
            cheie text NOT NULL CHECK (length(cheie) BETWEEN 1 AND 100),
            scor real NOT NULL CHECK (scor BETWEEN 0 AND 1),
            conform boolean NOT NULL,
            la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (promovare_id, etapa, grup, umbra, cheie)
        )"""
    )
    op.execute("CREATE INDEX promovari_observatii_etapa ON promovari_observatii (promovare_id, etapa, grup)")
    for t in TABELE:
        activeaza_rls(op.execute, t)
        op.execute(
            f"CREATE POLICY {t}_agentie ON {t} USING ((SELECT ama_agency())) WITH CHECK ((SELECT ama_agency()))"
        )
        op.execute(f"REVOKE ALL ON {t} FROM ama_app")
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {t} TO ama_app")


def downgrade() -> None:
    op.execute("DROP TABLE promovari_observatii")
    op.execute("DROP TABLE promovari")
