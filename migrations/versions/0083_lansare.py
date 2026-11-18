"""Lansarea comercială (F15.6, docs/25 §25.5): lista de go-live și studiile de caz

Revizia: 0083
Anterioara: 0082

- `verificari_lansare`: bifele manuale ale listei 25.5 (cine, când, cu ce notă); doar agenția (fără date de
  client). Punctele măsurabile nu se bifează de mână: se calculează (`app/lansare/golive.py`).
- `rezultate_avarie`: raportul pe scenarii al testelor de avarie (`scripts/avarie.sh`), pe mediu; doar agenția.
- `studii_caz`: studiul de caz al unui client (situație, acțiune, rezultat, cifrele măsurate), publicat doar cu
  acordul lui; RLS pe client.
"""

from alembic import op

from app.db.rls import activeaza_rls, activeaza_rls_tenant

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None

DOAR_AGENTIA = "((SELECT ama_agency()))"


def _doar_agentia(tabel: str) -> None:
    activeaza_rls(op.execute, tabel)
    op.execute(f"CREATE POLICY doar_agentia ON {tabel} USING {DOAR_AGENTIA} WITH CHECK {DOAR_AGENTIA}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {tabel} TO ama_app")


def upgrade() -> None:
    op.execute(
        """CREATE TABLE verificari_lansare (
            cod text PRIMARY KEY CHECK (cod ~ '^[A-Z][0-9]{1,2}$'),
            bifat boolean NOT NULL DEFAULT false,
            nota text NOT NULL DEFAULT '' CHECK (length(nota) <= 500),
            bifat_de uuid,
            bifat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    _doar_agentia("verificari_lansare")
    op.execute(
        """CREATE TABLE rezultate_avarie (
            id uuid PRIMARY KEY,
            mediu text NOT NULL CHECK (mediu IN ('local', 'staging', 'productie')),
            trecute integer NOT NULL CHECK (trecute >= 0),
            total integer NOT NULL CHECK (total >= trecute),
            raport jsonb NOT NULL CHECK (jsonb_typeof(raport) = 'object'),
            rulat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    _doar_agentia("rezultate_avarie")
    op.execute(
        """CREATE TABLE studii_caz (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9-]{3,80}$'),
            titlu text NOT NULL CHECK (length(titlu) BETWEEN 3 AND 120),
            situatie text NOT NULL CHECK (length(situatie) <= 3000),
            actiune text NOT NULL CHECK (length(actiune) <= 3000),
            rezultat text NOT NULL CHECK (length(rezultat) <= 3000),
            cifre jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(cifre) = 'object'),
            acord_client boolean NOT NULL DEFAULT false,
            stare text NOT NULL DEFAULT 'ciorna' CHECK (stare IN ('ciorna', 'publicat')),
            publicat_la timestamptz,
            creat_la timestamptz NOT NULL DEFAULT now(),
            CHECK (stare = 'ciorna' OR (acord_client AND publicat_la IS NOT NULL))
        )"""
    )
    activeaza_rls_tenant(op.execute, "studii_caz")


def downgrade() -> None:
    op.execute("DROP TABLE studii_caz")
    op.execute("DROP TABLE rezultate_avarie")
    op.execute("DROP TABLE verificari_lansare")
