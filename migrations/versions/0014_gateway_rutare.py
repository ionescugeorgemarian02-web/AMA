"""Gateway de modele: profilurile de sarcină și sănătatea furnizorilor (F3.4, docs/08 §8.2–8.3)

Revizia: 0014
Anterioara: 0013

- `gateway_profiluri`: profilurile din 8.2 ca date (nivel minim, capabilități, lanț ordonat de modele, ce se întâmplă
  când lanțul s-a epuizat, lanț de degradare). La nivel de agenție, ca restul registrului. Sămânța vine din
  `app/gateway/profiluri.py`.
- `gateway_furnizori`: coloanele întrerupătorului (erori consecutive, deschis până la) și ale sănătății (ultima eroare,
  ultimul succes). Se schimbă doar prin `app/gateway/sanatate.py`, cu instrucțiuni atomice.
"""

import sqlalchemy as sa
from alembic import op

from app.db.rls import activeaza_rls

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

AGENTIE = "(SELECT ama_agency())"
CITIRE = (
    "((SELECT ama_agency()) OR (SELECT ama_tenant_id()) IS NOT NULL OR (SELECT ama_user_id()) IS NOT NULL)"
)
CAPABILITATI = "ARRAY['iesire_structurata', 'unelte', 'viziune']::text[]"


def upgrade() -> None:
    op.execute(
        """ALTER TABLE gateway_furnizori
            ADD COLUMN erori_consecutive integer NOT NULL DEFAULT 0 CHECK (erori_consecutive >= 0),
            ADD COLUMN intrerupt_pana_la timestamptz,
            ADD COLUMN ultima_eroare_la timestamptz,
            ADD COLUMN ultimul_succes_la timestamptz"""
    )
    op.execute(
        f"""CREATE TABLE gateway_profiluri (
            nume text PRIMARY KEY CHECK (nume ~ '^[a-z][a-z0-9_]{{1,40}}$'),
            eticheta text NOT NULL CHECK (length(eticheta) BETWEEN 1 AND 120),
            descriere text NOT NULL DEFAULT '' CHECK (length(descriere) <= 500),
            nivel_min text NOT NULL CHECK (nivel_min IN ('T1', 'T2', 'T3', 'T4')),
            capabilitati text[] NOT NULL DEFAULT '{{}}' CHECK (capabilitati <@ {CAPABILITATI}),
            lant text[] NOT NULL CHECK (cardinality(lant) BETWEEN 1 AND 20),
            la_epuizare text NOT NULL CHECK (la_epuizare IN ('amana', 'degradeaza', 'amana_sau_provizoriu')),
            lant_degradare text[] NOT NULL DEFAULT '{{}}' CHECK (cardinality(lant_degradare) <= 20),
            verificare_in_plus boolean NOT NULL DEFAULT false,
            creat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT profil_degradare CHECK ((la_epuizare = 'amana') = (cardinality(lant_degradare) = 0))
        )"""
    )
    activeaza_rls(op.execute, "gateway_profiluri")
    op.execute(f"CREATE POLICY gateway_profiluri_citire ON gateway_profiluri FOR SELECT USING ({CITIRE})")
    op.execute(
        f"CREATE POLICY gateway_profiluri_adaugare ON gateway_profiluri FOR INSERT WITH CHECK ({AGENTIE})"
    )
    op.execute(
        f"CREATE POLICY gateway_profiluri_schimbare ON gateway_profiluri FOR UPDATE USING ({AGENTIE}) WITH CHECK ({AGENTIE})"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON gateway_profiluri TO ama_app")
    _semana()


def _semana() -> None:
    from app.gateway import profiluri

    conn = op.get_bind()
    conn.execute(sa.text("SELECT set_config('app.agency', '1', true)"))  # RLS forțat și pentru proprietar
    for p in profiluri.PROFILURI:
        conn.execute(
            sa.text(
                "INSERT INTO gateway_profiluri (nume, eticheta, descriere, nivel_min, capabilitati, lant, la_epuizare, "
                "lant_degradare, verificare_in_plus) VALUES (:nume, :eticheta, :descriere, :nivel_min, :capabilitati, "
                ":lant, :la_epuizare, :lant_degradare, :verificare) ON CONFLICT (nume) DO NOTHING"
            ),
            {
                "nume": p.nume, "eticheta": p.eticheta, "descriere": p.descriere, "nivel_min": p.nivel_min,
                "capabilitati": list(p.capabilitati), "lant": list(p.lant), "la_epuizare": p.la_epuizare,
                "lant_degradare": list(p.lant_degradare), "verificare": p.verificare_in_plus,
            },
        )  # fmt: skip


def downgrade() -> None:
    op.execute("DROP TABLE gateway_profiluri")
    op.execute(
        """ALTER TABLE gateway_furnizori
            DROP COLUMN erori_consecutive, DROP COLUMN intrerupt_pana_la,
            DROP COLUMN ultima_eroare_la, DROP COLUMN ultimul_succes_la"""
    )
