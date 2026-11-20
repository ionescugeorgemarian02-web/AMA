"""Rolul vizual și subiectul activelor, plus cererile de material lipsă ale storyboardului (F-editorial).

- `active.rol_vizual`: ce rol poate avea activul într-un material (`logo`, `fotografie`, `filmare`, `ilustratie`,
  `coperta`, `export`) sau NULL (incert, de clasificat de operator). Separat de `categorie` (tipul fișierului).
- `active.subiect`: ce se vede, pe scurt (de exemplu „transmisie: lanț pe pinion”), folosit la potrivirea scenelor.
- `cereri_material`: o scenă a unei prezentări fără material potrivit blochează livrabilul cu o cerere precisă
  („Încarcă o fotografie verticală cu …”), până la încărcare și reluare.
"""

from alembic import op

from app.db.rls import activeaza_rls_tenant

revision = "0142"
down_revision = "0141"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE active
        ADD COLUMN rol_vizual text CHECK (rol_vizual IN
            ('logo', 'fotografie', 'filmare', 'ilustratie', 'coperta', 'export')),
        ADD COLUMN subiect text NOT NULL DEFAULT ''""")
    op.execute("""UPDATE active SET rol_vizual = CASE
            WHEN sursa = 'identitate' THEN 'logo'
            WHEN sursa = 'compozitor' THEN 'coperta'
            WHEN sursa = 'montaj' THEN 'export'
            WHEN sursa = 'animatie' THEN 'ilustratie'
            WHEN sursa IN ('stock', 'generat') AND categorie = 'foto' THEN 'fotografie'
            WHEN sursa IN ('stock', 'generat') AND categorie = 'video' THEN 'filmare'
        END""")
    op.execute("""CREATE TABLE cereri_material (
        id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES clienti(id),
        livrabil_id uuid NOT NULL REFERENCES livrabile(id), versiune integer NOT NULL,
        scena integer NOT NULL CHECK (scena >= 0), subiect text NOT NULL, cerere text NOT NULL,
        stare text NOT NULL DEFAULT 'deschisa' CHECK (stare IN ('deschisa', 'rezolvata')),
        creat_la timestamptz NOT NULL DEFAULT now(), rezolvat_la timestamptz,
        UNIQUE (tenant_id, livrabil_id, versiune, scena))""")
    op.execute("CREATE INDEX cereri_material_deschise ON cereri_material(tenant_id) WHERE stare = 'deschisa'")
    activeaza_rls_tenant(op.execute, "cereri_material")


def downgrade() -> None:
    op.execute("DROP TABLE cereri_material")
    op.execute("ALTER TABLE active DROP COLUMN subiect, DROP COLUMN rol_vizual")
