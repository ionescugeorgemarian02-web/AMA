"""F2.1 — schema bibliotecii, drepturile lui `ama_app`, topologia web → bază → worker."""

import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError

from app.main import create_app
from app.operare import motor
from tests.chaos import fluxuri_proba as proba
from tests.conftest import BazaTest

pytestmark = pytest.mark.db


@pytest.fixture
def dir_proba(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("AMA_PROBA_DIR", str(tmp_path))
    return tmp_path


# ---- roluri și privilegii -------------------------------------------------------------------------------------


def test_schema_exista_si_apartine_proprietarului(admin_engine: Engine) -> None:
    with admin_engine.connect() as c:
        proprietari = (
            c.execute(text("SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname = 'dbos'"))
            .scalars()
            .all()
        )
        schema_owner = c.execute(
            text(
                "SELECT r.rolname FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner WHERE n.nspname = 'dbos'"
            )
        ).scalar_one()
    assert proprietari == ["ama_owner"] and schema_owner == "ama_owner"


def test_aplicatia_citeste_si_scrie_dar_nu_poate_modifica_structura(baza: BazaTest) -> None:
    engine = create_engine(baza.app_url)
    try:
        with engine.begin() as c:
            c.execute(text("SELECT count(*) FROM dbos.workflow_status")).scalar_one()
        for instructiune in (
            "CREATE TABLE dbos.intrus (x int)",
            "CREATE SCHEMA intrus",
            "TRUNCATE dbos.workflow_status",
            "DROP TABLE dbos.workflow_status",
            "ALTER TABLE dbos.workflow_status ADD COLUMN intrus int",
            "CREATE TABLE public.intrus (x int)",
        ):
            with pytest.raises(DBAPIError), engine.begin() as c:
                c.execute(text(instructiune))
    finally:
        engine.dispose()


def test_drepturile_pe_tabelele_bibliotecii_sunt_cele_minime(admin_engine: Engine) -> None:
    with admin_engine.connect() as c:
        drepturi = {
            r[0]
            for r in c.execute(
                text(
                    "SELECT DISTINCT privilege_type FROM information_schema.role_table_grants "
                    "WHERE grantee = 'ama_app' AND table_schema = 'dbos'"
                )
            )
        }
        creare = c.execute(text("SELECT has_schema_privilege('ama_app', 'dbos', 'CREATE')")).scalar_one()
        utilizare = c.execute(text("SELECT has_schema_privilege('ama_app', 'dbos', 'USAGE')")).scalar_one()
    assert drepturi == {"SELECT", "INSERT", "UPDATE", "DELETE"}
    assert utilizare is True and creare is False


def test_migrarea_sistemului_se_poate_repeta_si_pastreaza_drepturile(
    baza: BazaTest, admin_engine: Engine
) -> None:
    motor.migreaza_sistem(baza.owner_url)
    motor.migreaza_sistem(baza.owner_url)
    test_drepturile_pe_tabelele_bibliotecii_sunt_cele_minime(admin_engine)


def test_o_tabela_noua_a_bibliotecii_nu_primeste_drepturi_de_structura(
    baza: BazaTest, admin_engine: Engine
) -> None:
    """Drepturile implicite pentru tabelele viitoare (o versiune nouă a bibliotecii) sunt restrânse de la început."""
    owner = create_engine(baza.owner_url)
    try:
        with owner.begin() as c:
            c.execute(text("CREATE TABLE dbos.viitoare (x int)"))
        with admin_engine.connect() as c:
            drepturi = {
                r[0]
                for r in c.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE grantee = 'ama_app' AND table_name = 'viitoare'"
                    )
                )
            }
        assert drepturi == {"SELECT", "INSERT", "UPDATE", "DELETE"}
    finally:
        with owner.begin() as c:
            c.execute(text("DROP TABLE dbos.viitoare"))
        owner.dispose()


def test_workerul_refuza_sa_porneasca_pe_o_baza_fara_schema(
    baza_goala: BazaTest, config: Callable[..., None]
) -> None:
    """Aplicația nu are drept de DDL: fără pasul de migrare a sistemului, pornirea eșuează, nu creează nimic."""
    config(database_url=baza_goala.app_url, worker_id="worker-fara-schema")
    with pytest.raises(Exception, match=r"(?i)migrat|schema|dbos"):
        motor.porneste()
    assert not motor.pornit()


# ---- topologia: web doar pune în coadă ----------------------------------------------------------------------------


def test_aplicatia_web_porneste_fara_executor_si_pune_joburi_in_coada(
    baza: BazaTest, motor_curat: None, dir_proba: Path
) -> None:
    with TestClient(create_app()) as client:
        assert client.get("/healthz").status_code == 200
        assert not motor.pornit(), "procesul web nu pornește executorul"
        job = motor.trimite(proba.simplu, "web1", cheie="web-1")
        stare = motor.stare_flux(job)
    assert stare is not None and stare.stare is motor.StareJob.IN_COADA
    assert proba.numara("web1.simplu") == 0, "nimic nu rulează fără worker"


def test_aceeasi_cheie_de_doua_ori_este_acelasi_job(
    baza: BazaTest, motor_curat: None, admin_engine: Engine
) -> None:
    cheie = f"idem-{uuid.uuid4().hex[:8]}"
    a = motor.trimite(proba.simplu, "x", cheie=cheie)
    b = motor.trimite(proba.simplu, "x", cheie=cheie)
    assert a == b == cheie
    with admin_engine.connect() as c:
        n = c.execute(
            text("SELECT count(*) FROM dbos.workflow_status WHERE workflow_uuid = :i"), {"i": cheie}
        ).scalar_one()
    assert n == 1


def test_continutul_in_loc_de_identificator_este_refuzat_si_nu_ajunge_in_baza(
    baza: BazaTest, motor_curat: None, admin_engine: Engine
) -> None:
    with pytest.raises(motor.ArgumentNepermis):
        motor.trimite(proba.simplu, "un text lung " * 50, cheie="continut-1")
    with pytest.raises(motor.ArgumentNepermis):
        motor.trimite(proba.simplu, "ok", kwargs={"corp": {"a": {"b": 1}}}, cheie="continut-2")
    with admin_engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM dbos.workflow_status")).scalar_one() == 0


@pytest.mark.parametrize("cheie", ["", " ", "are spatiu", "a" * 200, "cu\nnewline"])
def test_cheie_nepermisa(baza: BazaTest, motor_curat: None, cheie: str) -> None:
    with pytest.raises(ValueError, match="cheie"):
        motor.trimite(proba.simplu, "x", cheie=cheie)


def test_functie_fara_decorator_nu_poate_fi_trimisa(baza: BazaTest) -> None:
    def oarecare(x: str) -> None: ...

    with pytest.raises(TypeError, match="nu este un flux"):
        motor.trimite(oarecare, "x")


# ---- executorul în proces: un flux de la cap la coadă -------------------------------------------------------------------


def test_un_flux_trimis_din_web_se_executa_in_worker(executor: None, dir_proba: Path) -> None:
    job = motor.trimite(proba.trei_pasi, "w1", cheie="exec-1")
    final = motor.asteapta_flux(job, timeout_sec=20)
    assert final.stare is motor.StareJob.TERMINAT and final.executor == "worker-local"
    assert proba.numara("w1.terminat") == 1 and proba.numara("w1.pas1") == 1


def test_pasii_se_reincearca_cu_pauza_crescatoare_si_eroarea_definitiva_nu(
    executor: None, dir_proba: Path
) -> None:
    job = motor.trimite(proba.cu_reincercari, "r1", cheie="reinc-1")
    assert motor.asteapta_flux(job, timeout_sec=20).stare is motor.StareJob.TERMINAT
    assert proba.numara("r1.incercare") == 3, "două eșecuri temporare, apoi reușita"

    job = motor.trimite(proba.cu_eroare_definitiva, "r2", cheie="reinc-2")
    final = motor.asteapta_flux(job, timeout_sec=20)
    assert final.stare is motor.StareJob.ESUAT and final.eroare and "EroareDefinitiva" in final.eroare
    assert proba.numara("r2.incercare") == 1, "o eroare definitivă nu se reîncearcă"

    job = motor.trimite(proba.cu_reincercari_epuizate, "r3", cheie="reinc-3")
    final = motor.asteapta_flux(job, timeout_sec=20)
    assert final.stare is motor.StareJob.ESUAT
    assert proba.numara("r3.incercare") == 3, "o încercare + 2 reîncercări, apoi eroarea ajunge la flux"


def test_pasul_cu_continut_este_refuzat(executor: None, dir_proba: Path) -> None:
    job = motor.trimite(proba.cu_continut_in_pas, "c1", cheie="cont-1")
    final = motor.asteapta_flux(job, timeout_sec=20)
    assert final.stare is motor.StareJob.ESUAT and final.eroare and "ArgumentNepermis" in final.eroare
