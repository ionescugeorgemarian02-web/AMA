"""Fixture-uri comune. Testele de bază de date rulează ca `ama_app`, pe o bază nouă pe sesiune."""

import atexit
import os
import secrets
import shutil
import tempfile
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url

from app.operare.motor.migrare import migreaza_sistem

os.environ.setdefault("AMA_ENV", "test")
os.environ.setdefault("AMA_EFECTE_PAUZA_SEC", "0.05")  # reîncercările efectelor, fără pauze lungi în teste

# Mediile din teste merg într-un director temporar, nu în `/var/lib/ama/media` (implicitul din producție:
# în CI rulăm fără drepturi de root și scrierea acolo pică cu PermissionError). Testele care vor alt loc
# îl suprascriu cu `monkeypatch.setenv("AMA_MEDIA_DIR", ...)`.
if "AMA_MEDIA_DIR" not in os.environ:
    _MEDIA_TEST = tempfile.mkdtemp(prefix="ama-media-test-")
    os.environ["AMA_MEDIA_DIR"] = _MEDIA_TEST
    atexit.register(shutil.rmtree, _MEDIA_TEST, ignore_errors=True)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def chei_de_test(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Chei de test construite la rulare (nu sunt secrete reale). Nu sunt globale: testele de configurare
    verifică tocmai lipsa lor."""
    from app.config import get_settings

    monkeypatch.setenv("AMA_MASTER_KEY", "test-" + "m" * 40)
    monkeypatch.setenv("AMA_SECRET_KEY", "test-" + "s" * 40)
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


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
            pytest.fail(
                "AMA_TEST_DATABASE_ADMIN_URL lipsește în CI: testele de bază nu au voie să fie sărite"
            )
        pytest.skip("AMA_TEST_DATABASE_ADMIN_URL lipsește (rulează `make test`)")
    return url


# Rolurile sunt ale întregului server, nu ale unei baze: parolele se generează o singură dată pe rulare.
# Dacă fiecare bază nouă le-ar schimba, conexiunile următoare spre baza de sesiune ar fi refuzate.
PAROLA_OWNER, PAROLA_APP = secrets.token_hex(16), secrets.token_hex(16)


def creeaza_baza_noua(admin: str, migreaza: bool) -> Iterator[BazaTest]:
    from app.db.bootstrap import pregateste_baza, pregateste_roluri

    nume = f"ama_test_{uuid.uuid4().hex[:12]}"
    parola_owner, parola_app = PAROLA_OWNER, PAROLA_APP
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
            nume,
            admin_baza,
            owner.render_as_string(hide_password=False),
            app.render_as_string(hide_password=False),
        )
        if migreaza:
            command.upgrade(alembic_config(baza.owner_url), "head")
            migreaza_sistem(baza.owner_url)  # schema bibliotecii de workflow-uri (F2.1), tot ca proprietar
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


@pytest.fixture(autouse=True)
def _fara_programari_declarate() -> Iterator[None]:
    """Programările declarate în cod sunt globale procesului: niciun test nu le lasă următorului."""
    from app.operare import motor

    motor.uita_declaratiile()
    yield
    motor.uita_declaratiile()


@pytest.fixture
def motor_curat(baza: BazaTest, admin_engine: Engine) -> Iterator[None]:
    """Joburile bibliotecii sunt comune întregii baze de test: fiecare test pornește fără joburi și fără programări.
    La final se închide clientul web (are motor propriu de conexiuni, legat de configurarea testului)."""
    from sqlalchemy import text

    from app.operare import motor

    def goleste() -> None:
        with admin_engine.begin() as c:
            c.execute(text("TRUNCATE dbos.workflow_status CASCADE"))
            c.execute(text("DELETE FROM dbos.workflow_schedules"))

    motor.inchide_client()
    goleste()
    yield
    motor.inchide_client()
    goleste()


@pytest.fixture
def porneste_executor(
    baza: BazaTest, motor_curat: None, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[..., None]]:
    """Fabrică: pornește executorul ÎN procesul testului (rapid), cu setări proprii (`culoare_greu=3` …).
    Testele de avarie (SIGKILL, SIGTERM) folosesc procese reale din `tests/chaos`."""
    from app.config import get_settings
    from app.operare import motor

    def pornire(**setari: object) -> None:
        mediu = {"motor_polling_sec": 0.1, "worker_id": "worker-local", **setari}
        for cheie, valoare in mediu.items():
            monkeypatch.setenv(f"AMA_{cheie.upper()}", str(valoare))
        get_settings.cache_clear()
        motor.porneste()

    yield pornire
    motor.opreste(0)
    get_settings.cache_clear()


@pytest.fixture
def executor(porneste_executor: Callable[..., None]) -> None:
    porneste_executor()
