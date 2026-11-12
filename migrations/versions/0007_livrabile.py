"""Livrabilele și istoricul tranzițiilor lor (F2.3, 7.2–7.3)

Revizia: 0007
Anterioara: 0006

- `livrabile`: identitate, stare, versiune și contoare (fără conținut: acela vine în F4–F6). Un declanșator în bază
  refuză orice schimbare de stare care nu e în tabelul de tranziții SAU nu trece prin `productie.muta` (aceasta
  setează `app.muta_livrabil` pe durata tranzacției).
- `livrabile_tranzitii`: istoric doar-adăugare (aplicate și refuzate).
- Perechile permise de mai jos sunt o copie înghețată a lui `app.productie.stari.TABEL` la data migrării; testul
  `tests/integration/test_productie_tranzitii.py` compară funcția din bază cu tabelul din cod. Când tabelul se
  schimbă, o migrare nouă redefinește funcția.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

PERECHI = {
    "aprobat": ("anulat", "coada_de_erori", "in_randare", "programat"),
    "asteapta_aprobare": ("anulat", "aprobat", "expirat", "respins"),
    "briefat": ("anulat", "coada_de_erori", "in_scriere"),
    "carantina": ("anulat", "coada_de_erori", "in_reparatie", "in_validare"),
    "coada_de_erori": (
        "anulat",
        "aprobat",
        "briefat",
        "control_media",
        "gata",
        "in_masurare",
        "in_publicare",
        "in_randare",
        "in_reparatie",
        "in_scriere",
        "in_validare",
        "programat",
        "publicat",
        "validat",
    ),
    "control_media": ("anulat", "carantina", "coada_de_erori", "esec_temporar", "gata", "in_randare"),
    "esec_temporar": (
        "anulat",
        "coada_de_erori",
        "control_media",
        "in_publicare",
        "in_randare",
        "in_reparatie",
        "in_scriere",
        "in_validare",
    ),
    "expirat": ("anulat", "planificat"),
    "gata": ("anulat", "coada_de_erori", "programat"),
    "in_masurare": ("coada_de_erori", "inchis"),
    "in_publicare": ("coada_de_erori", "esec_temporar", "publicat"),
    "in_randare": ("anulat", "coada_de_erori", "control_media", "esec_temporar"),
    "in_reparatie": ("anulat", "coada_de_erori", "esec_temporar", "in_validare"),
    "in_scriere": ("anulat", "coada_de_erori", "esec_temporar", "in_validare"),
    "in_validare": ("anulat", "carantina", "coada_de_erori", "esec_temporar", "in_reparatie", "validat"),
    "planificat": ("anulat", "briefat"),
    "programat": ("anulat", "coada_de_erori", "in_publicare"),
    "publicat": ("coada_de_erori", "in_masurare"),
    "validat": ("anulat", "aprobat", "asteapta_aprobare", "coada_de_erori", "expirat"),
}
STARI = (
    "planificat",
    "briefat",
    "in_scriere",
    "in_validare",
    "in_reparatie",
    "validat",
    "asteapta_aprobare",
    "aprobat",
    "in_randare",
    "control_media",
    "gata",
    "programat",
    "in_publicare",
    "publicat",
    "in_masurare",
    "inchis",
    "respins",
    "carantina",
    "esec_temporar",
    "coada_de_erori",
    "anulat",
    "expirat",
)
CLASE = (
    "publicare_continut",
    "raspuns_inbox",
    "schimbare_reclame",
    "schimbare_strategie",
    "cheltuiala",
)


def _lista(valori: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in valori)


def upgrade() -> None:
    if set(STARI) != set(PERECHI) | {"inchis", "respins", "anulat"}:
        raise RuntimeError("lista de stări și tabelul de perechi nu se potrivesc")
    values = ", ".join(f"('{d}', '{la}')" for d, ls in PERECHI.items() for la in ls)
    op.execute(
        f"""CREATE FUNCTION ama_livrabil_tranzitie_permisa(din text, la text) RETURNS boolean
            LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT (din, la) IN (VALUES {values}) $$"""
    )

    op.execute(
        f"""CREATE TABLE livrabile (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            tip text NOT NULL CHECK (tip ~ '^[a-z][a-z0-9_]{{1,39}}$'),
            canal text NOT NULL CHECK (canal ~ '^[a-z][a-z0-9_]{{1,39}}$'),
            clasa_actiune text NOT NULL DEFAULT 'publicare_continut' CHECK (clasa_actiune IN ({_lista(CLASE)})),
            termen_la timestamptz,
            stare text NOT NULL DEFAULT 'planificat' CHECK (stare IN ({_lista(STARI)})),
            stare_anterioara text CHECK (stare_anterioara IS NULL OR stare_anterioara IN ({_lista(STARI)})),
            versiune integer NOT NULL DEFAULT 1 CHECK (versiune >= 1),
            runde_reparatie integer NOT NULL DEFAULT 0 CHECK (runde_reparatie >= 0),
            predari integer NOT NULL DEFAULT 0 CHECK (predari >= 0),
            apeluri_llm integer NOT NULL DEFAULT 0 CHECK (apeluri_llm >= 0),
            timp_sec double precision NOT NULL DEFAULT 0 CHECK (timp_sec >= 0),
            buget_apeluri_llm integer NOT NULL CHECK (buget_apeluri_llm > 0),
            buget_timp_sec integer NOT NULL CHECK (buget_timp_sec > 0),
            escaladari integer NOT NULL DEFAULT 0 CHECK (escaladari >= 0),
            creat_la timestamptz NOT NULL DEFAULT now(),
            actualizat_la timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX livrabile_tenant_stare ON livrabile (tenant_id, stare)")
    op.execute("CREATE INDEX livrabile_tenant_creat ON livrabile (tenant_id, creat_la DESC)")
    op.execute(
        """CREATE FUNCTION ama_livrabil_garda() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.stare <> 'planificat' THEN
                    RAISE EXCEPTION 'un livrabil nou începe în starea planificat (nu %)', NEW.stare
                        USING ERRCODE = 'integrity_constraint_violation';
                END IF;
                RETURN NEW;
            END IF;
            IF NEW.id <> OLD.id OR NEW.tenant_id <> OLD.tenant_id THEN
                RAISE EXCEPTION 'identificatorul și clientul unui livrabil nu se schimbă'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF NEW.stare <> OLD.stare THEN
                IF coalesce(current_setting('app.muta_livrabil', true), '') <> NEW.id::text THEN
                    RAISE EXCEPTION 'starea livrabilului se schimbă doar prin productie.muta'
                        USING ERRCODE = 'integrity_constraint_violation';
                END IF;
                IF NOT ama_livrabil_tranzitie_permisa(OLD.stare, NEW.stare) THEN
                    RAISE EXCEPTION 'tranziție nepermisă: % -> %', OLD.stare, NEW.stare
                        USING ERRCODE = 'integrity_constraint_violation';
                END IF;
            END IF;
            RETURN NEW;
        END $$"""
    )
    op.execute(
        "CREATE TRIGGER livrabile_garda BEFORE INSERT OR UPDATE ON livrabile "
        "FOR EACH ROW EXECUTE FUNCTION ama_livrabil_garda()"
    )
    activeaza_rls_tenant(op.execute, "livrabile", drepturi="SELECT, INSERT, UPDATE")

    op.execute(
        f"""CREATE TABLE livrabile_tranzitii (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            livrabil_id uuid NOT NULL REFERENCES livrabile (id),
            rezultat text NOT NULL CHECK (rezultat IN ('aplicata', 'refuzata')),
            din text CHECK (din IS NULL OR din IN ({_lista(STARI)})),
            in_stare text NOT NULL CHECK (in_stare IN ({_lista(STARI)})),
            componenta text NOT NULL CHECK (length(componenta) BETWEEN 1 AND 60),
            actor_tip text NOT NULL CHECK (actor_tip IN ('componenta', 'utilizator', 'sistem')),
            utilizator_id uuid REFERENCES utilizatori (id),
            motiv text NOT NULL DEFAULT '' CHECK (length(motiv) <= 500),
            detalii jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            versiune integer NOT NULL,
            creat_la timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK (din IS NOT NULL OR rezultat = 'aplicata')
        )"""
    )
    op.execute("CREATE INDEX livrabile_tranzitii_livrabil ON livrabile_tranzitii (livrabil_id, creat_la)")
    op.execute(
        "CREATE INDEX livrabile_tranzitii_rezultate ON livrabile_tranzitii (creat_la) "
        "WHERE rezultat = 'aplicata' AND in_stare IN ('validat', 'coada_de_erori')"
    )
    op.execute(
        "CREATE TRIGGER livrabile_tranzitii_fara_modificari BEFORE UPDATE OR DELETE ON livrabile_tranzitii "
        "FOR EACH ROW EXECUTE FUNCTION ama_jurnal_doar_adaugare()"
    )
    op.execute(
        "CREATE TRIGGER livrabile_tranzitii_fara_golire BEFORE TRUNCATE ON livrabile_tranzitii "
        "FOR EACH STATEMENT EXECUTE FUNCTION ama_jurnal_doar_adaugare()"
    )
    activeaza_rls_tenant(op.execute, "livrabile_tranzitii", drepturi="SELECT, INSERT")


def downgrade() -> None:
    op.execute("DROP TABLE livrabile_tranzitii")
    op.execute("DROP TABLE livrabile")
    op.execute("DROP FUNCTION ama_livrabil_garda()")
    op.execute("DROP FUNCTION ama_livrabil_tranzitie_permisa(text, text)")
