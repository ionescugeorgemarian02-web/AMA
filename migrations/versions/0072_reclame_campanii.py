"""Reclame: campaniile construite, reclamele lor și propunerile de schimbare (F13.4, I2, docs/16 §16.1, §16.3)

Revizia: 0072
Anterioara: 0071

- `efecte_sistem.tip` primește `reclama`: scrierile la platformele de reclame pleacă prin același „outbox” (D-008).
- `reclame_campanii`: campania construită din planul aprobat (creată în pauză), cu id-ul de la platformă.
- `reclame_anunturi`: reclamele (creativele) unei campanii, cu varianta testată.
- `reclame_propuneri`: o schimbare tipizată (creare, stare, buget), cu starea de dinainte și de după, verdictul
  gardianului, efectul care o aplică și, la anulare, propunerea anulată.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE efecte_sistem DROP CONSTRAINT efecte_sistem_tip_check")
    op.execute(
        "ALTER TABLE efecte_sistem ADD CONSTRAINT efecte_sistem_tip_check CHECK (tip IN ('email', 'plata', 'reclama'))"
    )
    op.execute(
        """CREATE TABLE reclame_campanii (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            cont_id uuid NOT NULL REFERENCES reclame_conturi (id),
            plan_id uuid REFERENCES reclame_planuri (id),
            nume text NOT NULL CHECK (length(nume) BETWEEN 3 AND 160),
            rol text NOT NULL CHECK (rol IN ('scalare', 'test')),
            variabila text,
            id_extern text,
            stare text NOT NULL DEFAULT 'in_constructie'
                CHECK (stare IN ('in_constructie', 'in_pauza', 'activa', 'oprita', 'esuata')),
            buget_zilnic_bani bigint NOT NULL CHECK (buget_zilnic_bani > 0),
            creat_la timestamptz NOT NULL DEFAULT now(),
            schimbat_la timestamptz,
            UNIQUE (cont_id, nume)
        )"""
    )
    activeaza_rls_tenant(op.execute, "reclame_campanii")
    op.execute(
        """CREATE TABLE reclame_anunturi (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            campanie_id uuid NOT NULL REFERENCES reclame_campanii (id),
            nume text NOT NULL CHECK (length(nume) BETWEEN 3 AND 200),
            varianta text NOT NULL DEFAULT '',
            titlu text NOT NULL CHECK (length(titlu) BETWEEN 1 AND 120),
            text text NOT NULL CHECK (length(text) BETWEEN 1 AND 2000),
            link text NOT NULL CHECK (link ~ '^https://'),
            generat_ai boolean NOT NULL DEFAULT false,
            id_extern text,
            stare text NOT NULL DEFAULT 'in_constructie'
                CHECK (stare IN ('in_constructie', 'in_pauza', 'activa', 'oprita', 'blocata')),
            verificare jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(verificare) = 'array'),
            creat_la timestamptz NOT NULL DEFAULT now(),
            UNIQUE (campanie_id, nume)
        )"""
    )
    activeaza_rls_tenant(op.execute, "reclame_anunturi")
    op.execute(
        """CREATE TABLE reclame_propuneri (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES clienti (id),
            cont_id uuid NOT NULL REFERENCES reclame_conturi (id),
            campanie_id uuid NOT NULL REFERENCES reclame_campanii (id),
            anunt_id uuid REFERENCES reclame_anunturi (id),
            tip text NOT NULL CHECK (tip IN ('creeaza', 'stare', 'buget', 'stare_anunt')),
            inainte jsonb NOT NULL CHECK (jsonb_typeof(inainte) = 'object'),
            dupa jsonb NOT NULL CHECK (jsonb_typeof(dupa) = 'object'),
            motiv text NOT NULL CHECK (length(motiv) BETWEEN 3 AND 500),
            sursa text NOT NULL
                CHECK (sursa IN ('constructor', 'regula', 'strateg', 'consiliu', 'om', 'anulare', 'urgenta', 'test')),
            stare text NOT NULL DEFAULT 'propusa'
                CHECK (stare IN ('propusa', 'refuzata', 'aprobata', 'aplicata', 'esuata', 'anulata')),
            verdict jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(verdict) = 'object'),
            efect_id uuid REFERENCES efecte_sistem (id),
            anuleaza_id uuid REFERENCES reclame_propuneri (id),
            creat_la timestamptz NOT NULL DEFAULT now(),
            decis_de uuid REFERENCES utilizatori (id),
            decis_la timestamptz,
            aplicat_la timestamptz,
            CHECK ((stare = 'aplicata') = (aplicat_la IS NOT NULL))
        )"""
    )
    op.execute("CREATE INDEX reclame_propuneri_campanie ON reclame_propuneri (campanie_id, creat_la)")
    op.execute(
        "CREATE INDEX reclame_propuneri_deschise ON reclame_propuneri (stare) WHERE stare = 'aprobata'"
    )
    activeaza_rls_tenant(op.execute, "reclame_propuneri")


def downgrade() -> None:
    op.execute("DROP TABLE reclame_propuneri")
    op.execute("DROP TABLE reclame_anunturi")
    op.execute("DROP TABLE reclame_campanii")
    op.execute("DELETE FROM efecte_sistem WHERE tip = 'reclama'")
    op.execute("ALTER TABLE efecte_sistem DROP CONSTRAINT efecte_sistem_tip_check")
    op.execute(
        "ALTER TABLE efecte_sistem ADD CONSTRAINT efecte_sistem_tip_check CHECK (tip IN ('email', 'plata'))"
    )
