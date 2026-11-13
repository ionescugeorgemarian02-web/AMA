"""Cercetare: sursele, colectările și documentele colectate (F4.2, docs/12 §12.3, docs/20 §20.2, §20.4)

Revizia: 0022
Anterioara: 0021

- `surse`: sursele unui client (un site sau materiale manuale), cu statutul din 12.1 (cod, ca dată, în `statut.py`).
- `colectari`: o rulare a colectorului pe o sursă (stare, limite, contoare derivate din paginile ei).
- `colectari_pagini`: fiecare adresă găsită și soarta ei: în așteptare / citită / sărită (cu motiv) / nemodificată /
  duplicat / eroare. Ea este și frontiera durabilă a colectării (se reia după cădere fără să refacă paginile terminate).
- `documente_colectate`: textul extras (în bază) și calea originalului de pe disc, hash-uri, antete, versiunea. Un
  document pe (sursă, adresă); același text în aceeași sursă nu se păstrează de două ori. `expira_la`: păstrarea de
  90 de zile a documentelor din exterior (20.4); ștergerea efectivă este un job ulterior.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE surse (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            tip text NOT NULL CHECK (tip IN ('site', 'manual')),
            statut text NOT NULL CHECK (statut ~ '^[a-z][a-z_]{2,39}$'),
            nume text NOT NULL CHECK (length(nume) BETWEEN 1 AND 200),
            url_radacina text CHECK (length(url_radacina) <= 2000),
            activa boolean NOT NULL DEFAULT true,
            creat_la timestamptz NOT NULL DEFAULT now(),
            creat_de uuid REFERENCES utilizatori (id),
            CONSTRAINT surse_site_are_url CHECK ((tip = 'site') = (url_radacina IS NOT NULL))
        )"""
    )
    op.execute("CREATE INDEX surse_client ON surse (tenant_id, creat_la)")
    activeaza_rls_tenant(op.execute, "surse", drepturi="SELECT, INSERT, UPDATE")

    op.execute(
        """CREATE TABLE colectari (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            sursa_id uuid NOT NULL REFERENCES surse (id),
            stare text NOT NULL DEFAULT 'in_asteptare'
                CHECK (stare IN ('in_asteptare', 'in_curs', 'terminata', 'esuata')),
            limite jsonb NOT NULL DEFAULT '{}'::jsonb,
            user_agent text NOT NULL,
            motiv_oprire text NOT NULL DEFAULT '' CHECK (length(motiv_oprire) <= 200),
            pagini_gasite integer NOT NULL DEFAULT 0,
            pagini_citite integer NOT NULL DEFAULT 0,
            pagini_sarite integer NOT NULL DEFAULT 0,
            pagini_nemodificate integer NOT NULL DEFAULT 0,
            pagini_duplicate integer NOT NULL DEFAULT 0,
            linkuri_ignorate integer NOT NULL DEFAULT 0,
            octeti_cititi bigint NOT NULL DEFAULT 0,
            cereri_http integer NOT NULL DEFAULT 0,
            creat_la timestamptz NOT NULL DEFAULT now(),
            creat_de uuid REFERENCES utilizatori (id),
            inceput_la timestamptz,
            sfarsit_la timestamptz
        )"""
    )
    op.execute("CREATE INDEX colectari_sursa ON colectari (sursa_id, creat_la DESC)")
    activeaza_rls_tenant(op.execute, "colectari", drepturi="SELECT, INSERT, UPDATE")

    op.execute(
        """CREATE TABLE documente_colectate (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            sursa_id uuid NOT NULL REFERENCES surse (id),
            tip text NOT NULL CHECK (tip IN ('pagina', 'text_lipit', 'fisier')),
            url text CHECK (length(url) <= 2000),
            titlu text NOT NULL DEFAULT '' CHECK (length(titlu) <= 300),
            text text NOT NULL CHECK (length(text) BETWEEN 1 AND 500000),
            hash_continut text NOT NULL CHECK (hash_continut ~ '^[0-9a-f]{64}$'),
            hash_text text NOT NULL CHECK (hash_text ~ '^[0-9a-f]{64}$'),
            content_type text NOT NULL DEFAULT '',
            octeti integer NOT NULL DEFAULT 0 CHECK (octeti >= 0),
            cale_original text CHECK (length(cale_original) <= 300),
            antete jsonb NOT NULL DEFAULT '{}'::jsonb,
            versiune integer NOT NULL DEFAULT 1 CHECK (versiune >= 1),
            colectare_id uuid REFERENCES colectari (id),
            colectat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            verificat_la timestamptz NOT NULL DEFAULT now(),
            expira_la timestamptz,
            creat_de uuid REFERENCES utilizatori (id),
            CONSTRAINT documente_pagina_are_url CHECK ((tip = 'pagina') = (url IS NOT NULL))
        )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX documente_url ON documente_colectate (sursa_id, url) WHERE url IS NOT NULL"
    )
    op.execute("CREATE UNIQUE INDEX documente_text ON documente_colectate (sursa_id, hash_text)")
    op.execute("CREATE INDEX documente_client ON documente_colectate (tenant_id, sursa_id)")
    activeaza_rls_tenant(op.execute, "documente_colectate", drepturi="SELECT, INSERT, UPDATE")

    op.execute(
        """CREATE TABLE colectari_pagini (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            colectare_id uuid NOT NULL REFERENCES colectari (id),
            url text NOT NULL CHECK (length(url) <= 2000),
            adancime integer NOT NULL DEFAULT 0 CHECK (adancime >= 0),
            gasit_din text CHECK (length(gasit_din) <= 2000),
            stare text NOT NULL DEFAULT 'in_asteptare'
                CHECK (stare IN ('in_asteptare', 'citita', 'sarita', 'nemodificata', 'duplicat', 'eroare')),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 60),
            detaliu text NOT NULL DEFAULT '' CHECK (length(detaliu) <= 300),
            cod_http integer,
            document_id uuid REFERENCES documente_colectate (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            procesat_la timestamptz,
            UNIQUE (colectare_id, url)
        )"""
    )
    op.execute("CREATE INDEX colectari_pagini_coada ON colectari_pagini (colectare_id, stare, adancime, id)")
    activeaza_rls_tenant(op.execute, "colectari_pagini", drepturi="SELECT, INSERT, UPDATE")


def downgrade() -> None:
    op.execute("DROP TABLE colectari_pagini")
    op.execute("DROP TABLE documente_colectate")
    op.execute("DROP TABLE colectari")
    op.execute("DROP TABLE surse")
