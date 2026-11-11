"""F1.4 — plasă de siguranță: un tabel nou fără RLS pică testele (AGENTS.md, „Interzis”)."""

import pytest
from sqlalchemy import Engine, text

pytestmark = [pytest.mark.db, pytest.mark.isolation]

# Singurul tabel din schemă fără RLS: evidența migrărilor (proprietarul o folosește; aplicația nu are drepturi pe ea).
FARA_RLS = {"alembic_version"}

CATALOG = """
SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
       (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS politici,
       EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attname = 'tenant_id'
               AND a.attnum > 0 AND NOT a.attisdropped) AS are_tenant
FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r', 'p')
"""


def test_tabelele_cu_tenant_id_au_rls_activ_fortat_si_politica(admin_engine: Engine) -> None:
    with admin_engine.connect() as c:
        rows = c.execute(text(CATALOG)).all()
    tabele = [r for r in rows if r.are_tenant]
    assert {r.relname for r in tabele} >= {"apartenente", "alocari"}, "catalogul nu arată tabelele așteptate"
    gresite = [
        r.relname for r in tabele if not (r.relrowsecurity and r.relforcerowsecurity and r.politici > 0)
    ]
    assert not gresite, f"tabele cu tenant_id fără RLS activ+forțat+politică: {gresite}"


def test_toate_tabelele_din_schema_au_rls(admin_engine: Engine) -> None:
    with admin_engine.connect() as c:
        rows = c.execute(text(CATALOG)).all()
    gresite = [
        r.relname
        for r in rows
        if r.relname not in FARA_RLS and not (r.relrowsecurity and r.relforcerowsecurity and r.politici > 0)
    ]
    assert not gresite, f"tabele fără RLS (adaugă-l în migrare sau în lista explicită): {gresite}"


def test_nicio_politica_nu_este_literal_adevarata(admin_engine: Engine) -> None:
    with admin_engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT polrelid::regclass::text AS tabel, polname, pg_get_expr(polqual, polrelid) AS q, "
                "pg_get_expr(polwithcheck, polrelid) AS w FROM pg_policy"
            )
        ).all()
    deschise = [
        (r.tabel, r.polname)
        for r in rows
        if (r.q or "").strip("() ") == "true" or (r.w or "").strip("() ") == "true"
    ]
    assert not deschise, f"politici care permit tot: {deschise}"


def test_politicile_nu_se_aplica_rolului_public_si_aplicatia_nu_detine_tabele(admin_engine: Engine) -> None:
    with admin_engine.connect() as c:
        detinute = c.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner "
                "WHERE r.rolname = 'ama_app' AND c.relnamespace = 'public'::regnamespace"
            )
        ).all()
        privilegii = c.execute(
            text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = 'ama_app'")
        ).scalar_one()
    assert not detinute
    assert privilegii is False
