"""Gateway de modele: registrul de furnizori și modele (F3.1, docs/08 §8.1)

Revizia: 0012
Anterioara: 0011

- `gateway_furnizori`: un furnizor de modele (nume, tip de API, adresă, stare, termeni de folosire, limite comune
  contului). Cheia de API NU stă în bază: `cheie_env` este doar numele variabilei de mediu (AMA_CHEIE_*), iar baza
  refuză orice alt nume (nu se poate trimite gateway-ul la `AMA_MASTER_KEY`). Un furnizor fără uz comercial confirmat
  nu poate fi `activ` (impus și aici, nu doar în cod).
- `gateway_modele`: modelele unui furnizor: nivel T1–T4/local, context, capabilități, limite, preț-umbră, scor pe
  profil (îl umple F3.6).
- Registrul este la nivel de agenție (ca `opriri`): citit din orice context cu identitate (utilizator, client sau
  agenție; lucrătorii deschid sesiuni de client), scris doar de scopul de agenție. Fără `tenant_id`: nu ține date de
  client. Sămânța vine din `app/gateway/inventar.py` (date cu marcajele [V]/[S]/[I] și data verificării).
"""

import json

import sqlalchemy as sa
from alembic import op

from app.db.rls import activeaza_rls

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"
CITIRE = (
    "((SELECT ama_agency()) OR (SELECT ama_tenant_id()) IS NOT NULL OR (SELECT ama_user_id()) IS NOT NULL)"
)
CAPABILITATI = "ARRAY['iesire_structurata', 'unelte', 'viziune']::text[]"


def _politici(tabel: str) -> None:
    activeaza_rls(op.execute, tabel)
    op.execute(f"CREATE POLICY {tabel}_citire ON {tabel} FOR SELECT USING ({CITIRE})")
    op.execute(f"CREATE POLICY {tabel}_adaugare ON {tabel} FOR INSERT WITH CHECK ({AGENTIE})")
    op.execute(
        f"CREATE POLICY {tabel}_schimbare ON {tabel} FOR UPDATE USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {tabel} TO ama_app")


def upgrade() -> None:
    op.execute(
        """CREATE TABLE gateway_furnizori (
            id uuid PRIMARY KEY,
            cod text NOT NULL UNIQUE CHECK (cod ~ '^[a-z][a-z0-9_]{1,30}$'),
            nume text NOT NULL CHECK (length(nume) BETWEEN 1 AND 120),
            tip_api text NOT NULL CHECK (tip_api ~ '^[a-z][a-z0-9_]{1,30}$'),
            url_baza text NOT NULL CHECK (url_baza ~ '^https://' AND length(url_baza) <= 300),
            cheie_env text NOT NULL CHECK (cheie_env ~ '^AMA_CHEIE_[A-Z0-9_]{1,40}$'),
            stare text NOT NULL DEFAULT 'inactiv' CHECK (stare IN ('activ', 'inactiv', 'pauza')),
            stare_motiv text NOT NULL DEFAULT '' CHECK (length(stare_motiv) <= 300),
            platit boolean NOT NULL DEFAULT false,
            uz_comercial boolean,
            antrenare_pe_date boolean,
            restrictii_regionale text NOT NULL DEFAULT '' CHECK (length(restrictii_regionale) <= 500),
            note text NOT NULL DEFAULT '' CHECK (length(note) <= 1000),
            marcaj text NOT NULL CHECK (marcaj IN ('V', 'S', 'I')),
            verificat_la date,
            sursa text NOT NULL DEFAULT '' CHECK (length(sursa) <= 300),
            cereri_minut integer CHECK (cereri_minut > 0),
            cereri_zi integer CHECK (cereri_zi > 0),
            tokeni_minut bigint CHECK (tokeni_minut > 0),
            tokeni_zi bigint CHECK (tokeni_zi > 0),
            reset_zi_ora smallint NOT NULL DEFAULT 0 CHECK (reset_zi_ora BETWEEN 0 AND 23),
            parametri jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (octet_length(parametri::text) <= 2000),
            creat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT furnizor_activ_cere_uz_comercial CHECK (stare <> 'activ' OR uz_comercial IS TRUE)
        )"""
    )
    _politici("gateway_furnizori")

    op.execute(
        f"""CREATE TABLE gateway_modele (
            id uuid PRIMARY KEY,
            furnizor_id uuid NOT NULL REFERENCES gateway_furnizori (id),
            identificator text NOT NULL CHECK (length(identificator) BETWEEN 1 AND 200),
            nume_afisat text NOT NULL CHECK (length(nume_afisat) BETWEEN 1 AND 120),
            nivel text NOT NULL CHECK (nivel IN ('T1', 'T2', 'T3', 'T4', 'local')),
            context_tokeni integer NOT NULL CHECK (context_tokeni > 0),
            capabilitati text[] NOT NULL DEFAULT '{{}}' CHECK (capabilitati <@ {CAPABILITATI}),
            activ boolean NOT NULL DEFAULT true,
            cereri_minut integer CHECK (cereri_minut > 0),
            cereri_zi integer CHECK (cereri_zi > 0),
            tokeni_minut bigint CHECK (tokeni_minut > 0),
            tokeni_zi bigint CHECK (tokeni_zi > 0),
            pret_umbra_intrare numeric(10, 4) NOT NULL DEFAULT 0 CHECK (pret_umbra_intrare >= 0),
            pret_umbra_iesire numeric(10, 4) NOT NULL DEFAULT 0 CHECK (pret_umbra_iesire >= 0),
            scor jsonb NOT NULL DEFAULT '{{}}'::jsonb CHECK (jsonb_typeof(scor) = 'object'),
            marcaj text NOT NULL CHECK (marcaj IN ('V', 'S', 'I')),
            verificat_la date,
            sursa text NOT NULL DEFAULT '' CHECK (length(sursa) <= 300),
            note text NOT NULL DEFAULT '' CHECK (length(note) <= 500),
            creat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT model_unic UNIQUE (furnizor_id, identificator)
        )"""
    )
    _politici("gateway_modele")
    _semana()


def _semana() -> None:
    """Sămânța: inserează ce lipsește (nu suprascrie nimic). Coloanele sunt cele de mai sus, nu cele de mâine."""
    from app.gateway import inventar
    from app.ids import new_id

    conn = op.get_bind()
    # RLS este FORȚAT și pentru proprietar: sămânța scrie ca „agenție”, doar în tranzacția migrării.
    conn.execute(sa.text("SELECT set_config('app.agency', '1', true)"))
    ids: dict[str, object] = {}
    for f in inventar.FURNIZORI:
        ids[f.cod] = new_id()
        conn.execute(
            sa.text(
                "INSERT INTO gateway_furnizori (id, cod, nume, tip_api, url_baza, cheie_env, platit, uz_comercial, "
                "antrenare_pe_date, restrictii_regionale, note, marcaj, verificat_la, sursa, cereri_minut, cereri_zi, "
                "tokeni_minut, tokeni_zi, reset_zi_ora, parametri) VALUES (:id, :cod, :nume, :tip_api, :url_baza, "
                ":cheie_env, :platit, :uz_comercial, :antrenare_pe_date, :restrictii_regionale, :note, :marcaj, "
                ":verificat_la, :sursa, :cereri_minut, :cereri_zi, :tokeni_minut, :tokeni_zi, :reset_zi_ora, "
                "CAST(:parametri AS jsonb)) ON CONFLICT (cod) DO NOTHING"
            ),
            {
                "id": ids[f.cod], "cod": f.cod, "nume": f.nume, "tip_api": f.tip_api, "url_baza": f.url_baza,
                "cheie_env": f.cheie_env, "platit": f.platit, "uz_comercial": f.uz_comercial,
                "antrenare_pe_date": f.antrenare_pe_date, "restrictii_regionale": f.restrictii_regionale,
                "note": f.note, "marcaj": f.marcaj, "verificat_la": f.verificat_la, "sursa": f.sursa,
                "cereri_minut": f.limite.cereri_minut, "cereri_zi": f.limite.cereri_zi,
                "tokeni_minut": f.limite.tokeni_minut, "tokeni_zi": f.limite.tokeni_zi,
                "reset_zi_ora": f.reset_zi_ora, "parametri": json.dumps(f.parametri),
            },
        )  # fmt: skip
    for m in inventar.MODELE:
        conn.execute(
            sa.text(
                "INSERT INTO gateway_modele (id, furnizor_id, identificator, nume_afisat, nivel, context_tokeni, "
                "capabilitati, cereri_minut, cereri_zi, tokeni_minut, tokeni_zi, pret_umbra_intrare, "
                "pret_umbra_iesire, marcaj, verificat_la, sursa, note) VALUES (:id, "
                "(SELECT id FROM gateway_furnizori WHERE cod = :furnizor), :identificator, :nume_afisat, :nivel, "
                ":context_tokeni, :capabilitati, :cereri_minut, :cereri_zi, :tokeni_minut, :tokeni_zi, :pi, :pe, "
                ":marcaj, :verificat_la, :sursa, :note) ON CONFLICT (furnizor_id, identificator) DO NOTHING"
            ),
            {
                "id": new_id(), "furnizor": m.furnizor, "identificator": m.identificator,
                "nume_afisat": m.nume_afisat, "nivel": m.nivel, "context_tokeni": m.context_tokeni,
                "capabilitati": list(m.capabilitati), "cereri_minut": m.limite.cereri_minut,
                "cereri_zi": m.limite.cereri_zi, "tokeni_minut": m.limite.tokeni_minut,
                "tokeni_zi": m.limite.tokeni_zi, "pi": m.pret_umbra_intrare, "pe": m.pret_umbra_iesire,
                "marcaj": m.marcaj, "verificat_la": m.verificat_la, "sursa": m.sursa, "note": m.note,
            },
        )  # fmt: skip


def downgrade() -> None:
    op.execute("DROP TABLE gateway_modele")
    op.execute("DROP TABLE gateway_furnizori")
