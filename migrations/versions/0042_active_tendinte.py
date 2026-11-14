"""Materialele clientului: biblioteca de active și inboxul de tendințe (F7.5, docs/19 §19.2, ADR-15)

Revizia: 0042
Anterioara: 0041

- `active`: fișierele încărcate (fotografii, video, documente), verificate după conținut, pe disc local
  (`AMA_MEDIA_DIR/<client>/active/<sha256>.<ext>`), cu sursa (cine, de unde, numele original). Un hash pe client.
- `tendinte`: linkurile și ideile lipite de client în portal (intră în cercetare, F10).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE active (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            categorie text NOT NULL CHECK (categorie IN ('foto', 'video', 'document')),
            mime text NOT NULL,
            marime bigint NOT NULL CHECK (marime > 0),
            sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            cale text NOT NULL,
            nume_original text NOT NULL CHECK (length(nume_original) <= 200),
            sursa text NOT NULL CHECK (sursa ~ '^[a-z_]{3,40}$'),
            descriere text NOT NULL DEFAULT '',
            incarcat_de uuid REFERENCES utilizatori (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, sha256)
        )"""
    )
    activeaza_rls_tenant(op.execute, "active")
    op.execute(
        """CREATE TABLE tendinte (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            text text NOT NULL CHECK (length(text) BETWEEN 3 AND 2000),
            url text CHECK (url IS NULL OR (url ~ '^https?://' AND length(url) <= 500)),
            stare text NOT NULL DEFAULT 'noua' CHECK (stare IN ('noua', 'folosita', 'ignorata')),
            creat_de uuid REFERENCES utilizatori (id),
            creat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    activeaza_rls_tenant(op.execute, "tendinte")


def downgrade() -> None:
    op.execute("DROP TABLE tendinte")
    op.execute("DROP TABLE active")
