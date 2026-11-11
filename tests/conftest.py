"""Fixture-uri comune. Testele de bază de date rulează ca `ama_app`, pe o bază nouă pe sesiune."""

import os
import secrets
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url

os.environ.setdefault("AMA_ENV", "test")
# Chei de test construite la rulare (nu sunt secrete reale; scanerul de secrete nu trebuie slăbit).
os.environ.setdefault("AMA_MASTER_KEY", "test-" + "m" * 40)
os.environ.setdefault("AMA_SECRET_KEY", "test-" + "s" * 40)

ROOT = Path(__file__).resolve().parents[1]


def alembic_config(owner_url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.attributes["url"] = owner_url
    return cfg


@dataclass(frozen=True)
class BazaTest:
    nume: str
    admin_url: str  # superutilizator, spre baza de test (ocolește RLS: doar pentru pregătire și verificare)
    owner_url: str
    app_url: str


def _psycopg_dsn(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def admin_url() -> str:
    url = os.environ.get("AMA_TEST_DATABASE_ADMIN_URL")
    if not url:
        if os.environ.get("CI"):
            pytest.fail("AMA_TEST_DATABASE_ADMIN_URL lipsește în CI: testele de bază nu au voie să fie sărite")
        pytest.skip("AMA_TEST_DATABASE_ADMIN_URL lipsește (rulează `make test`)")
    return url


def creeaza_baza_noua(admin: str, migreaza: bool) -> Iterator[BazaTest]:
    from app.db.bootstrap import pregateste_baza, pregateste_roluri

    nume = f"ama_test_{uuid.uuid4().hex[:12]}"
    parola_owner, parola_app = secrets.token_hex(16), secrets.token_hex(16)
    base = make_url(admin)
    pregateste_roluri(_psycopg_dsn(admin), parola_owner=parola_owner, parola_app=parola_app)
    with psycopg.connect(_psycopg_dsn(admin), autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{nume}" OWNER ama_owner TEMPLATE template0')
    try:
        admin_baza = base.set(database=nume).render_as_string(hide_password=False)
        pregateste_baza(_psycopg_dsn(admin_baza), nume)
        owner = base.set(database=nume, username="ama_owner", password=parola_owner)
        app = base.set(database=nume, username="ama_app", password=parola_app)
        baza = BazaTest(
            nume, admin_baza, owner.render_as_string(hide_password=False), app.render_as_string(hide_password=False)
        )
        if migreaza:
            command.upgrade(alembic_config(baza.owner_url), "head")
        yield baza
    finally:
        with psycopg.connect(_psycopg_dsn(admin), autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{nume}" WITH (FORCE)')


@pytest.fixture
def baza_goala(admin_url: str) -> Iterator[BazaTest]:
    """O bază proaspătă, fără migrări (pentru testele de migrare)."""
    yield from creeaza_baza_noua(admin_url, migreaza=False)


@pytest.fixture(scope="session")
def baza(admin_url: str) -> Iterator[BazaTest]:
    """Baza migrată la `head`; aplicația (`get_settings`, `app.db`) este îndreptată spre ea."""
    from app.config import get_settings
    from app.db import reset_engine

    mp = pytest.MonkeyPatch()
    try:
        for b in creeaza_baza_noua(admin_url, migreaza=True):
            mp.setenv("AMA_DATABASE_URL", b.app_url)
            mp.setenv("AMA_DATABASE_OWNER_URL", b.owner_url)
            get_settings.cache_clear()
            reset_engine()
            yield b
            reset_engine()
            get_settings.cache_clear()
    finally:
        mp.undo()


@pytest.fixture(scope="session")
def admin_engine(baza: BazaTest) -> Iterator[Engine]:
    """Superutilizator spre baza de test: doar pentru a pregăti/verifica date, nu pentru codul testat."""
    engine = create_engine(baza.admin_url)
    yield engine
    engine.dispose()
