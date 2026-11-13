"""Creierul: pasaje, vectori și căutare hibridă (F4.3, docs/10 §10.5)

Revizia: 0023
Anterioara: 0022

- `pasaje`: bucățile de text ale documentelor colectate (legătură pasaj → document → sursă, poziție și decalaje de
  caractere), cu `text_normalizat` (fără diacritice) pentru căutarea lexicală și coloana `embedding` (pgvector). Dimensiunea
  coloanei vine din registrul gateway-ului (`gateway_modele.dimensiune_vector` al modelului de vectori; 384 în sămânță).
  Fiecare vector poartă `model_vectori` (modelul care l-a produs): la schimbarea modelului pasajele se re-vectorizează.
- Căutarea lexicală: `fts` (tsvector cu configurația `simple` peste textul normalizat: fără dicționar românesc, deci
  „ș / ş / s” sunt același lucru) și `pg_trgm` (toleranță la forme flexionate și greșeli).
- Fără index vectorial aproximativ (HNSW / IVFFlat): căutarea filtrează ÎNTÂI pe client (RLS + `tenant_id`), iar un index
  global aproximativ ar tăia rezultatele după filtrare. Căutarea exactă pe pasajele unui client este corectă și rapidă la
  scara unui VPS (zeci de mii de pasaje pe client); un index parțial pe client se adaugă când un client o depășește.
"""

import sqlalchemy as sa
from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

DIMENSIUNE_IMPLICITA = 384


def _dimensiune() -> int:
    r = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT max(dimensiune_vector) FROM gateway_modele WHERE 'embeddings' = ANY(capabilitati)"
            )
        )
        .scalar()
    )
    return int(r or DIMENSIUNE_IMPLICITA)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")  # creată de pregătirea bazei; aici doar se verifică
    dim = _dimensiune()
    op.execute(
        f"""CREATE TABLE pasaje (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            sursa_id uuid NOT NULL REFERENCES surse (id),
            document_id uuid NOT NULL REFERENCES documente_colectate (id),
            pozitie integer NOT NULL CHECK (pozitie >= 0),
            car_inceput integer NOT NULL CHECK (car_inceput >= 0),
            car_sfarsit integer NOT NULL,
            text text NOT NULL CHECK (length(text) BETWEEN 1 AND 20000),
            text_normalizat text NOT NULL,
            hash_document text NOT NULL CHECK (hash_document ~ '^[0-9a-f]{{64}}$'),
            compartiment text CHECK (compartiment ~ '^[a-z][a-z_]{{2,39}}$'),
            embedding vector({dim}),
            model_vectori text CHECK (length(model_vectori) BETWEEN 1 AND 200),
            vectorizat_la timestamptz,
            fts tsvector GENERATED ALWAYS AS (to_tsvector('simple', text_normalizat)) STORED,
            creat_la timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pasaje_decalaje CHECK (car_sfarsit > car_inceput),
            CONSTRAINT pasaje_vector_si_model CHECK ((embedding IS NULL) = (model_vectori IS NULL)),
            UNIQUE (document_id, hash_document, pozitie)
        )"""
    )
    op.execute("CREATE INDEX pasaje_client_sursa ON pasaje (tenant_id, sursa_id)")
    op.execute("CREATE INDEX pasaje_document ON pasaje (document_id)")
    op.execute("CREATE INDEX pasaje_de_vectorizat ON pasaje (tenant_id, sursa_id) WHERE embedding IS NULL")
    op.execute("CREATE INDEX pasaje_fts ON pasaje USING gin (fts)")
    op.execute("CREATE INDEX pasaje_trigrame ON pasaje USING gin (text_normalizat gin_trgm_ops)")
    activeaza_rls_tenant(op.execute, "pasaje", drepturi="SELECT, INSERT, UPDATE, DELETE")


def downgrade() -> None:
    op.execute("DROP TABLE pasaje")
