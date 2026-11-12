"""Gateway de modele: modelul local și modelul de vectori (F3.5, docs/06 §6.3–6.4, docs/08 §8.1, docs/10 §10.5)

Revizia: 0018
Anterioara: 0017

- `gateway_furnizori.url_baza`: pe lângă `https://`, se acceptă `http://` DOAR spre un nume de serviciu intern (un singur
  cuvânt, fără puncte) sau spre `localhost` / `127.0.0.1`: serverul local de inferență rulează în rețeaua internă a stivei.
- `gateway_modele.capabilitati`: capabilitate nouă, `embeddings` (model de vectori; nu generează text).
- `gateway_modele`: `tokeni_pe_secunda` + `viteza_masurata_la` (viteza măsurată a modelelor locale, comanda
  `python -m app.gateway.masurare`) și `dimensiune_vector` (dimensiunea vectorilor, ca dată în registru).
- Sămânță (`app/gateway/inventar_local.py`, totul `[I]`, `inactiv`): furnizorul `local` cu trei mărimi de model și furnizorul
  `vectori` cu un model multilingv mic de 384 de dimensiuni.
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

URL_NOU = (
    "url_baza ~ '^(https://|http://([a-z][a-z0-9-]*|localhost|127\\.0\\.0\\.1)(:[0-9]{1,5})?/)' "
    "AND length(url_baza) <= 300"
)
CAPABILITATI_NOI = "ARRAY['iesire_structurata', 'unelte', 'viziune', 'embeddings']::text[]"
CAPABILITATI_VECHI = "ARRAY['iesire_structurata', 'unelte', 'viziune']::text[]"


def upgrade() -> None:
    op.execute("ALTER TABLE gateway_furnizori DROP CONSTRAINT gateway_furnizori_url_baza_check")
    op.execute(
        f"ALTER TABLE gateway_furnizori ADD CONSTRAINT gateway_furnizori_url_baza_check CHECK ({URL_NOU})"
    )
    op.execute("ALTER TABLE gateway_modele DROP CONSTRAINT gateway_modele_capabilitati_check")
    op.execute(
        "ALTER TABLE gateway_modele ADD CONSTRAINT gateway_modele_capabilitati_check "
        f"CHECK (capabilitati <@ {CAPABILITATI_NOI})"
    )
    op.execute(
        "ALTER TABLE gateway_modele ADD COLUMN tokeni_pe_secunda numeric(10, 2) CHECK (tokeni_pe_secunda >= 0)"
    )
    op.execute("ALTER TABLE gateway_modele ADD COLUMN viteza_masurata_la timestamptz")
    op.execute(
        "ALTER TABLE gateway_modele ADD COLUMN dimensiune_vector smallint "
        "CHECK (dimensiune_vector BETWEEN 1 AND 4096)"
    )
    _semana()


def _semana() -> None:
    from app.gateway import inventar_local
    from app.ids import new_id

    conn = op.get_bind()
    conn.execute(sa.text("SELECT set_config('app.agency', '1', true)"))
    ids: dict[str, object] = {}
    for f in inventar_local.FURNIZORI:
        ids[f["cod"]] = new_id()
        conn.execute(
            sa.text(
                "INSERT INTO gateway_furnizori (id, cod, nume, tip_api, url_baza, cheie_env, platit, uz_comercial, "
                "antrenare_pe_date, note, marcaj, parametri) VALUES (:id, :cod, :nume, :tip_api, :url_baza, "
                ":cheie_env, :platit, :uz_comercial, :antrenare_pe_date, :note, 'I', CAST(:parametri AS jsonb)) "
                "ON CONFLICT (cod) DO NOTHING"
            ),
            {
                **{k: v for k, v in f.items() if k != "parametri"},
                "id": ids[f["cod"]],
                "parametri": json.dumps(f["parametri"]),
            },
        )
    for furnizor, ident, nume, ctx, capab, dim, pi, pe in inventar_local.MODELE:
        conn.execute(
            sa.text(
                "INSERT INTO gateway_modele (id, furnizor_id, identificator, nume_afisat, nivel, context_tokeni, "
                "capabilitati, dimensiune_vector, pret_umbra_intrare, pret_umbra_iesire, marcaj) "
                "SELECT :id, f.id, :ident, :nume, 'local', :ctx, :capab, :dim, :pi, :pe, 'I' "
                "FROM gateway_furnizori f WHERE f.cod = :furnizor ON CONFLICT (furnizor_id, identificator) DO NOTHING"
            ),
            {"id": new_id(), "furnizor": furnizor, "ident": ident, "nume": nume, "ctx": ctx, "capab": list(capab),
             "dim": dim, "pi": pi, "pe": pe},
        )  # fmt: skip


def downgrade() -> None:
    # Registrul nu are politică de DELETE (nici pentru agenție): sămânța locală se șterge fără RLS, doar aici.
    for tabel in ("gateway_modele", "gateway_furnizori"):
        op.execute(f"ALTER TABLE {tabel} NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "DELETE FROM gateway_modele WHERE furnizor_id IN "
        "(SELECT id FROM gateway_furnizori WHERE cod IN ('local', 'vectori'))"
    )
    op.execute("DELETE FROM gateway_furnizori WHERE cod IN ('local', 'vectori')")
    for tabel in ("gateway_modele", "gateway_furnizori"):
        op.execute(f"ALTER TABLE {tabel} FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gateway_modele DROP COLUMN dimensiune_vector")
    op.execute("ALTER TABLE gateway_modele DROP COLUMN viteza_masurata_la")
    op.execute("ALTER TABLE gateway_modele DROP COLUMN tokeni_pe_secunda")
    op.execute("ALTER TABLE gateway_modele DROP CONSTRAINT gateway_modele_capabilitati_check")
    op.execute(
        "ALTER TABLE gateway_modele ADD CONSTRAINT gateway_modele_capabilitati_check "
        f"CHECK (capabilitati <@ {CAPABILITATI_VECHI})"
    )
    op.execute("ALTER TABLE gateway_furnizori DROP CONSTRAINT gateway_furnizori_url_baza_check")
    op.execute(
        "ALTER TABLE gateway_furnizori ADD CONSTRAINT gateway_furnizori_url_baza_check "
        "CHECK (url_baza ~ '^https://' AND length(url_baza) <= 300)"
    )
