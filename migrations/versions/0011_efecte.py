"""Executorul de efecte externe (F2.5, 7.3, 7.5)

Revizia: 0011
Anterioara: 0010

- `efecte_de_trimis`: „outbox”-ul. Un rând = un efect extern cerut (de exemplu o publicare), scris în aceeași
  tranzacție cu schimbarea de stare care îl cere. `cheia` (client:livrabil:canal:versiune:tip) este unică în bază: a
  doua cerere pentru același efect găsește rândul primei. Stările și tranzițiile lor sunt ca în
  `app/operare/efecte/stari.py` (copiate aici ca date; un test le compară). Terminalele (`trimis`, `anulat`) nu se
  mai schimbă, iar identitatea efectului (client, livrabil, canal, versiune, tip, cheie, conținut) este neschimbabilă.
- `conectori_pauze`: canalul unui client pus pe pauză după o eroare de autentificare (se cere reautorizare).
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

STARI = ("in_asteptare", "in_trimitere", "trimis", "esuat_temporar", "esuat_definitiv", "anulat")
TIPURI = ("publicare",)
# (din, în): copia din `stari.TABEL` a efectelor.
TRANZITII = (
    ("in_asteptare", "in_trimitere"),
    ("in_asteptare", "anulat"),
    ("in_trimitere", "in_asteptare"),
    ("in_trimitere", "trimis"),
    ("in_trimitere", "esuat_temporar"),
    ("in_trimitere", "esuat_definitiv"),
    ("in_trimitere", "anulat"),
    ("esuat_temporar", "in_trimitere"),
    ("esuat_temporar", "trimis"),
    ("esuat_temporar", "esuat_definitiv"),
    ("esuat_temporar", "anulat"),
    ("esuat_definitiv", "in_asteptare"),
    ("esuat_definitiv", "trimis"),
    ("esuat_definitiv", "anulat"),
)


def _lista(valori: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in valori)


def upgrade() -> None:
    op.execute(
        f"""CREATE TABLE efecte_de_trimis (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            canal text NOT NULL CHECK (canal ~ '^[a-z][a-z0-9_]{{1,40}}$'),
            versiune integer NOT NULL CHECK (versiune >= 1),
            tip text NOT NULL CHECK (tip IN ({_lista(TIPURI)})),
            cheia text NOT NULL CHECK (length(cheia) <= 300),
            stare text NOT NULL DEFAULT 'in_asteptare' CHECK (stare IN ({_lista(STARI)})),
            payload jsonb NOT NULL DEFAULT '{{}}'::jsonb CHECK (octet_length(payload::text) <= 16384),
            incercari integer NOT NULL DEFAULT 0 CHECK (incercari >= 0),
            rulari integer NOT NULL DEFAULT 0 CHECK (rulari >= 0),
            programat_la timestamptz,
            id_extern text,
            link text,
            eroare_cod text,
            eroare_mesaj text CHECK (eroare_mesaj IS NULL OR length(eroare_mesaj) <= 500),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 300),
            creat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_la timestamptz NOT NULL DEFAULT now(),
            trimis_la timestamptz,
            CONSTRAINT efecte_cheia_unica UNIQUE (cheia),
            CHECK ((stare = 'trimis') = (id_extern IS NOT NULL))
        )"""
    )
    op.execute("CREATE INDEX efecte_stare ON efecte_de_trimis (stare, actualizat_la)")
    op.execute("CREATE INDEX efecte_livrabil ON efecte_de_trimis (livrabil_id, creat_la)")
    perechi = ", ".join(f"('{d}', '{la}')" for d, la in TRANZITII)
    op.execute(
        f"""CREATE FUNCTION ama_efect_garda() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.id <> OLD.id OR NEW.tenant_id <> OLD.tenant_id OR NEW.livrabil_id <> OLD.livrabil_id
               OR NEW.canal <> OLD.canal OR NEW.versiune <> OLD.versiune OR NEW.tip <> OLD.tip
               OR NEW.cheia <> OLD.cheia OR NEW.payload <> OLD.payload THEN
                RAISE EXCEPTION 'identitatea unui efect nu se schimbă (%)', OLD.id
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF NEW.stare <> OLD.stare AND (OLD.stare, NEW.stare) NOT IN ({perechi}) THEN
                RAISE EXCEPTION 'tranziție nepermisă a efectului %: % -> %', OLD.id, OLD.stare, NEW.stare
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF OLD.stare IN ('trimis', 'anulat') AND (to_jsonb(NEW) - 'actualizat_la') <> (to_jsonb(OLD) - 'actualizat_la') THEN
                RAISE EXCEPTION 'efectul % este în starea finală %', OLD.id, OLD.stare
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER efecte_garda BEFORE UPDATE ON efecte_de_trimis FOR EACH ROW EXECUTE FUNCTION ama_efect_garda()"
    )
    activeaza_rls_tenant(op.execute, "efecte_de_trimis", drepturi="SELECT, INSERT, UPDATE")

    op.execute(
        """CREATE TABLE conectori_pauze (
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            canal text NOT NULL CHECK (canal ~ '^[a-z][a-z0-9_]{1,40}$'),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 300),
            de_la timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, canal)
        )"""
    )
    activeaza_rls_tenant(op.execute, "conectori_pauze", drepturi="SELECT, INSERT, UPDATE, DELETE")


def downgrade() -> None:
    op.execute("DROP TABLE conectori_pauze")
    op.execute("DROP TABLE efecte_de_trimis")
    op.execute("DROP FUNCTION ama_efect_garda()")
