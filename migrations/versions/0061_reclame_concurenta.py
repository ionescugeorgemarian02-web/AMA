"""Analistul de reclame ale concurenței: concurenții urmăriți și reclamele observate (F10.8, C3, docs/12 §12.6)

Revizia: 0061
Anterioara: 0060

- `concurenti_reclame`: pe client, concurenții urmăriți în biblioteca de reclame (numele și pagina Meta).
- `reclame_observate`: reclamele citite din biblioteca oficială: textul, platformele, perioada de livrare,
  formatul și unghiul (pe reguli). Textul intră și în documentele colectate ale clientului, sub o sursă cu
  statut nereutilizabil, ca G7 să blocheze un text prea apropiat (`document_id`).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE concurenti_reclame (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            nume text NOT NULL CHECK (length(nume) BETWEEN 2 AND 120),
            pagina_meta text NOT NULL CHECK (pagina_meta ~ '^[0-9]{5,25}$'),
            creat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, pagina_meta)
        )"""
    )
    activeaza_rls_tenant(op.execute, "concurenti_reclame", drepturi="SELECT, INSERT, UPDATE, DELETE")
    op.execute(
        """CREATE TABLE reclame_observate (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            concurent_id uuid NOT NULL REFERENCES concurenti_reclame (id) ON DELETE CASCADE,
            id_extern text NOT NULL CHECK (length(id_extern) BETWEEN 1 AND 100),
            text text NOT NULL CHECK (length(text) BETWEEN 1 AND 5000),
            platforme text[] NOT NULL DEFAULT '{}',
            format text NOT NULL DEFAULT 'necunoscut' CHECK (format IN ('imagine', 'video', 'carusel', 'necunoscut')),
            unghi text NOT NULL CHECK (unghi ~ '^[a-z_]{3,30}$'),
            prima_livrare date NOT NULL,
            ultima_livrare date,
            document_id uuid,
            vazut_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, id_extern),
            CHECK (ultima_livrare IS NULL OR ultima_livrare >= prima_livrare)
        )"""
    )
    op.execute("CREATE INDEX reclame_observate_concurent ON reclame_observate (tenant_id, concurent_id)")
    activeaza_rls_tenant(op.execute, "reclame_observate", drepturi="SELECT, INSERT, UPDATE, DELETE")


def downgrade() -> None:
    op.execute("DROP TABLE reclame_observate")
    op.execute("DROP TABLE concurenti_reclame")
