"""Cercetătorul de tendințe: profilul de nișă al clientului și fișele de tendință (F10.7, C2, docs/12)

Revizia: 0060
Anterioara: 0059

- `tendinte_profil`: pe client, cuvintele-cheie ale nișei (cu ele se măsoară potrivirea) și fluxurile RSS de
  nișă urmărite.
- `fise_tendinta`: fișa din 12.5: subiect, dovezi cu linkuri, prima apariție, potrivirea cu nișa, risc, unghiul
  propus, termenul de valabilitate, semnalul (`slab` = o singură sursă, `confirmat` = cel puțin două). O fișă
  pe (client, subiect, zi). `inbox_id` leagă fișa de intrarea din inboxul de tendințe din care a pornit;
  `propunere` ține propunerea de calendar.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE tendinte_profil (
            tenant_id uuid PRIMARY KEY REFERENCES clienti (id),
            termeni text[] NOT NULL DEFAULT '{}' CHECK (cardinality(termeni) <= 40),
            fluxuri text[] NOT NULL DEFAULT '{}' CHECK (cardinality(fluxuri) <= 10),
            actualizat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    activeaza_rls_tenant(op.execute, "tendinte_profil")
    op.execute(
        """CREATE TABLE fise_tendinta (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            zi date NOT NULL,
            cheie text NOT NULL CHECK (length(cheie) BETWEEN 1 AND 200),
            subiect text NOT NULL CHECK (length(subiect) BETWEEN 2 AND 300),
            origine text NOT NULL CHECK (origine IN ('surse', 'inbox')),
            dovezi jsonb NOT NULL CHECK (jsonb_typeof(dovezi) = 'array'),
            prima_aparitie date NOT NULL,
            scor_nisa real NOT NULL CHECK (scor_nisa BETWEEN 0 AND 1),
            termeni_potriviti text[] NOT NULL DEFAULT '{}',
            semnal text NOT NULL CHECK (semnal IN ('slab', 'confirmat')),
            risc text NOT NULL CHECK (risc IN ('scazut', 'drepturi', 'sensibil')),
            unghi text NOT NULL DEFAULT '' CHECK (length(unghi) <= 400),
            valabil_pana date NOT NULL,
            stare text NOT NULL DEFAULT 'noua' CHECK (stare IN ('noua', 'folosita', 'ignorata', 'exclusa')),
            propunere jsonb,
            inbox_id uuid REFERENCES tendinte (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fise_tendinta_unic UNIQUE (tenant_id, cheie, zi),
            CONSTRAINT fise_tendinta_sensibil_exclus CHECK (risc <> 'sensibil' OR stare = 'exclusa')
        )"""
    )
    op.execute("CREATE INDEX fise_tendinta_zi ON fise_tendinta (tenant_id, zi DESC)")
    activeaza_rls_tenant(op.execute, "fise_tendinta")


def downgrade() -> None:
    op.execute("DROP TABLE fise_tendinta")
    op.execute("DROP TABLE tendinte_profil")
