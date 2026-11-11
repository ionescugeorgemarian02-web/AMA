"""F1.3 — migrările merg înainte și înapoi; rolurile și funcțiile de context sunt cum trebuie."""

import os
import uuid

import pytest
from alembic import command
from sqlalchemy import Engine, create_engine, text

from tests.conftest import BazaTest, alembic_config

pytestmark = pytest.mark.db

TABELE = "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
FUNCTII = (
    "SELECT count(*) FROM pg_proc WHERE proname LIKE 'ama\\_%' AND pronamespace = 'public'::regnamespace"
)


def test_migrarea_urca_coboara_si_urca_din_nou(baza_goala: BazaTest) -> None:
    cfg = alembic_config(baza_goala.owner_url)
    engine = create_engine(baza_goala.owner_url)
    try:
        command.upgrade(cfg, "head")
        with engine.connect() as c:
            assert c.execute(text(TABELE)).scalar_one() > 0
        command.downgrade(cfg, "base")
        with engine.connect() as c:
            assert c.execute(text(TABELE)).scalar_one() == 0
            assert c.execute(text(FUNCTII)).scalar_one() == 0
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()


def test_fiecare_migrare_poate_fi_coborata_pe_rand(baza_goala: BazaTest) -> None:
    from alembic.script import ScriptDirectory

    cfg = alembic_config(baza_goala.owner_url)
    revizii = [r.revision for r in reversed(list(ScriptDirectory.from_config(cfg).walk_revisions()))]
    for rev in revizii:
        command.upgrade(cfg, rev)
    for _ in revizii:
        command.downgrade(cfg, "-1")


def test_rolul_aplicatiei_nu_poate_ocoli_izolarea(admin_engine: Engine, baza: BazaTest) -> None:
    with admin_engine.connect() as c:
        rol = c.execute(
            text(
                "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname = 'ama_app'"
            )
        ).one()
        assert tuple(rol) == (False, False, False, False)
        proprietar = c.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'ama_owner'")
        ).one()
        assert tuple(proprietar) == (False, False)
        detinute = c.execute(
            text(
                "SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner WHERE r.rolname = 'ama_app'"
            )
        ).scalar_one()
        assert detinute == 0


@pytest.mark.parametrize(
    ("setari", "asteptat"),
    [
        ({}, (None, None, False, False)),
        ({"app.tenant_id": "", "app.agency": ""}, (None, None, False, False)),
        ({"app.tenant_id": "nu-e-uuid", "app.user_id": "'; DROP TABLE x;--"}, (None, None, False, False)),
        ({"app.agency": "da", "app.auth": "true"}, (None, None, False, False)),
        ({"app.agency": "1", "app.auth": "1"}, (None, None, True, True)),
    ],
)
def test_functiile_de_context_sunt_sigure(
    baza: BazaTest, setari: dict[str, str], asteptat: tuple[object, object, bool, bool]
) -> None:
    engine = create_engine(baza.app_url)
    try:
        with engine.connect() as c:
            for k, v in setari.items():
                c.execute(text("SELECT set_config(:k, :v, true)"), {"k": k, "v": v})
            r = c.execute(text("SELECT ama_tenant_id(), ama_user_id(), ama_agency(), ama_auth()")).one()
            assert tuple(r) == asteptat
    finally:
        engine.dispose()


def test_functiile_de_context_citesc_uuid_valid(baza: BazaTest) -> None:
    valoare = uuid.uuid4()
    engine = create_engine(baza.app_url)
    try:
        with engine.connect() as c:
            c.execute(text("SELECT set_config('app.tenant_id', :v, true)"), {"v": str(valoare)})
            assert c.execute(text("SELECT ama_tenant_id()")).scalar_one() == valoare
    finally:
        engine.dispose()


def test_contextul_este_local_tranzactiei(baza: BazaTest) -> None:
    from app.db import ContextDb, sesiune

    t = uuid.uuid4()
    with sesiune(ContextDb(tenant_id=t, agency=True)) as s:
        assert s.execute(text("SELECT ama_tenant_id()")).scalar_one() == t
        s.commit()  # tranzacție nouă în aceeași sesiune: contextul se reaplică
        assert s.execute(text("SELECT ama_agency()")).scalar_one() is True
    with sesiune() as s:  # aceeași conexiune din pool, fără context: nu a rămas nimic
        assert s.execute(text("SELECT ama_tenant_id(), ama_agency()")).one() == (None, False)


def test_extensiile_necesare(admin_engine: Engine) -> None:
    with admin_engine.connect() as c:
        instalate = {r[0] for r in c.execute(text("SELECT extname FROM pg_extension"))}
    assert {"pg_trgm", "citext"} <= instalate


def test_pgvector_disponibil(admin_engine: Engine) -> None:
    with admin_engine.connect() as c:
        disponibila = c.execute(text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")).first()
        instalata = c.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).first()
    if os.environ.get("AMA_REQUIRE_PGVECTOR") == "1":
        assert disponibila is not None, "AMA_REQUIRE_PGVECTOR=1, dar extensia `vector` nu este disponibilă"
        assert instalata is not None, "`vector` este disponibilă, dar nu a fost instalată de pregătirea bazei"
    elif disponibila is None:
        pytest.skip("pgvector indisponibil local; este obligatoriu în CI (AMA_REQUIRE_PGVECTOR=1)")
    else:
        assert instalata is not None
