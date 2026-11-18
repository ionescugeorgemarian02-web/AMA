"""Gateway-ul „pool” (G-pool): seiful de secrete și catalogul de furnizori gratuiți

Revizia: 0109
Anterioara: 0108

- `gateway_seif`: secretele furnizorilor, criptate (Fernet, cheie derivată din `AMA_MASTER_KEY`, care NU stă în
  bază). Doar numele din `catalog.NUME_SECRETE`. Tabel al agenției, fără `tenant_id`: RLS forțat, politici doar
  pentru agenție (clienții nu văd nici numele);
- sămânța catalogului `app.gateway.catalog`: furnizorii noi (NVIDIA NIM, SambaNova, Mistral, Kilo, LLM7, Z.ai,
  Ollama, SEA-LION) și modelele lor, plus modelele noi ale furnizorilor existenți. Toți pornesc `inactiv`, cu
  uzul comercial neconfirmat (marcaj `I`): proprietarul confirmă termenii și activează (8.1). Nu suprascrie;
- profilurile de sarcină primesc la coadă intrarea `rezerva:<profil>` (rezervele din catalog, familiile
  alternate), dacă au loc în lanț (maximum 20 de intrări).

Downgrade: scoate intrările `rezerva:`, modelele semănate aici fără evaluări, furnizorii rămași fără modele și
seiful.
"""

import json

import sqlalchemy as sa
from alembic import op

from app.db.rls import activeaza_rls

revision = "0109"
down_revision = "0108"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"
SURSA = "catalog G-pool"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE gateway_seif (
            nume text PRIMARY KEY CHECK (nume ~ '^[A-Z][A-Z0-9_]{2,60}$'),
            valoare bytea NOT NULL CHECK (octet_length(valoare) BETWEEN 1 AND 8192),
            creat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    activeaza_rls(op.execute, "gateway_seif")
    op.execute(f"CREATE POLICY gateway_seif_agentie ON gateway_seif USING ({AGENTIE}) WITH CHECK ({AGENTIE})")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON gateway_seif TO ama_app")
    _semana()


def _semana() -> None:
    from app.gateway import catalog
    from app.ids import new_id

    conn = op.get_bind()
    conn.execute(sa.text("SELECT set_config('app.agency', '1', true)"))
    for f in catalog.FURNIZORI_POOL:
        conn.execute(
            sa.text(
                "INSERT INTO gateway_furnizori (id, cod, nume, tip_api, url_baza, cheie_env, platit, uz_comercial, "
                "antrenare_pe_date, restrictii_regionale, note, marcaj, verificat_la, sursa, cereri_minut, "
                "cereri_zi, parametri) VALUES (:id, :cod, :nume, :tip_api, :url_baza, :cheie_env, false, NULL, "
                "NULL, '', :note, 'I', NULL, :sursa, :cereri_minut, :cereri_zi, CAST(:parametri AS jsonb)) "
                "ON CONFLICT (cod) DO NOTHING"
            ),
            {
                "id": new_id(), "cod": f.cod, "nume": f.nume, "tip_api": f.tip_api, "url_baza": f.url_baza,
                "cheie_env": f"AMA_CHEIE_{f.cod.upper()}",
                "note": (f"[G-pool] Secrete: {', '.join(f.secrete)}. {f.note}").strip()[:500],
                "sursa": SURSA, "cereri_minut": f.cereri_minut, "cereri_zi": f.cereri_zi,
                "parametri": json.dumps(dict.fromkeys(f.parametri_din.values(), "")),
            },
        )  # fmt: skip
    for m in catalog.MODELE_POOL:
        d = catalog.descriere_seed(m)
        conn.execute(
            sa.text(
                "INSERT INTO gateway_modele (id, furnizor_id, identificator, nume_afisat, nivel, context_tokeni, "
                "capabilitati, cereri_minut, cereri_zi, tokeni_minut, tokeni_zi, marcaj, sursa, note) VALUES (:id, "
                "(SELECT id FROM gateway_furnizori WHERE cod = :furnizor), :identificator, :nume_afisat, :nivel, "
                ":context_tokeni, :capabilitati, :cereri_minut, :cereri_zi, :tokeni_minut, :tokeni_zi, 'I', "
                ":sursa, :note) ON CONFLICT (furnizor_id, identificator) DO NOTHING"
            ),
            {"id": new_id(), "sursa": SURSA, **d},
        )
    for rol in catalog.ROLURI:
        conn.execute(
            sa.text(
                "UPDATE gateway_profiluri SET lant = array_append(lant, :intrare), actualizat_la = now() "
                "WHERE nume = :rol AND NOT (:intrare = ANY (lant)) AND cardinality(lant) < 20"
            ),
            {"rol": rol, "intrare": f"rezerva:{rol}"},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("SELECT set_config('app.agency', '1', true)"))
    conn.execute(
        sa.text(
            "UPDATE gateway_profiluri SET lant = array_remove(lant, 'rezerva:' || nume) "
            "WHERE ('rezerva:' || nume) = ANY (lant)"
        )
    )
    conn.execute(
        sa.text(
            "DELETE FROM gateway_modele m WHERE m.sursa = :s AND NOT EXISTS "
            "(SELECT 1 FROM gateway_evaluari_rulari e WHERE e.model_id = m.id)"
        ),
        {"s": SURSA},
    )
    conn.execute(
        sa.text(
            "DELETE FROM gateway_furnizori f WHERE f.sursa = :s AND NOT EXISTS "
            "(SELECT 1 FROM gateway_modele m WHERE m.furnizor_id = f.id)"
        ),
        {"s": SURSA},
    )
    op.execute("DROP TABLE gateway_seif")
