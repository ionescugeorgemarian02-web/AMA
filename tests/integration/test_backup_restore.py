"""F1.9 — circuit real: copie criptată -> destinație locală -> bază ștearsă -> restaurare de test -> verificare.

Folosește Postgres-ul de test (AMA_TEST_DATABASE_ADMIN_URL), pg_dump/psql/pg_restore, age și rclone reale.
Se sare peste test doar dacă o unealtă lipsește cu adevărat și variabila CI nu este setată.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ("pg_dump", "pg_restore", "psql", "age", "age-keygen", "rclone", "tar")
ADMIN = os.environ.get("AMA_TEST_DATABASE_ADMIN_URL", "")

_missing = [t for t in TOOLS if shutil.which(t) is None]
if _missing and not os.environ.get("CI"):
    pytest.skip(f"lipsesc uneltele: {', '.join(_missing)}", allow_module_level=True)
if not ADMIN:
    if os.environ.get("CI"):
        pytest.fail("AMA_TEST_DATABASE_ADMIN_URL nu este setată în CI")
    pytest.skip("AMA_TEST_DATABASE_ADMIN_URL nu este setată", allow_module_level=True)

spec = importlib.util.spec_from_file_location("ama_backup", ROOT / "infra" / "backup" / "ama_backup.py")
assert spec and spec.loader
ama_backup = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ama_backup  # necesar pentru @dataclass
spec.loader.exec_module(ama_backup)


def _url(dbname: str) -> str:
    return ama_backup.with_database(ADMIN, dbname)


def _psql(dbname: str, sql: str) -> str:
    r = subprocess.run(
        ["psql", "--dbname", _url(dbname), "-v", "ON_ERROR_STOP=1", "-At", "-c", sql],
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


def _keygen(path: Path) -> str:
    r = subprocess.run(["age-keygen", "-o", str(path)], capture_output=True, text=True, check=True)
    return (r.stderr + r.stdout).split("Public key:")[1].split()[0]


@pytest.fixture
def env(tmp_path: Path):
    db = f"ama_bk_{uuid.uuid4().hex[:8]}"
    _psql("postgres", f'CREATE DATABASE "{db}"')
    _psql(db, "CREATE TABLE marcaj (id int primary key, text text); INSERT INTO marcaj VALUES (1, 'salut backup')")
    media = tmp_path / "media"
    (media / "client-a").mkdir(parents=True)
    (media / "client-a" / "poza.bin").write_bytes(b"\x00\x01media")
    conf = tmp_path / "conf"
    conf.mkdir()
    (conf / "app.env").write_text("AMA_SECRET_KEY=CHANGE_ME\n")
    identity = tmp_path / "verificare.key"
    pub = _keygen(identity)
    cfg = ama_backup.Config(
        database_url=_url(db),
        dest=str(tmp_path / "destinatie"),
        recipients=[pub],
        media_dir=media,
        config_paths=[conf],
        workdir=tmp_path / "work",
        status_dir=tmp_path / "status",
        admin_url=_url("postgres"),
        identity_file=identity,
        verify_sql="SELECT count(*) FROM marcaj WHERE text = 'salut backup'",
        mediu="test",
        versiune="t1",
    )
    yield cfg, db, tmp_path
    _psql("postgres", f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')


def _scratch_dbs() -> str:
    return _psql("postgres", "SELECT count(*) FROM pg_database WHERE datname LIKE 'ama_restoretest_%'")


def test_circuit_complet_backup_si_restaurare(env) -> None:
    cfg, db, tmp = env
    result = ama_backup.run_op("backup", cfg)
    assert result["stare"] == "reusit", result["eroare"]
    snap = result["id"]
    stored = sorted(p.name for p in (tmp / "destinatie" / snap).iterdir())
    assert stored == ["baza.dump.age", "configurare.tar.gz.age", "manifest.json", "media.tar.gz.age"]
    # necriptat nu rămâne nimic și conținutul este criptat de-adevăratelea
    assert b"salut backup" not in (tmp / "destinatie" / snap / "baza.dump.age").read_bytes()
    assert not (tmp / "work" / snap).exists()
    saved = json.loads((tmp / "status" / "ultimul-backup.json").read_text())
    assert saved["schema"] == "ama.backup/1" and saved["tip"] == "backup" and saved["stare"] == "reusit"

    _psql("postgres", f'DROP DATABASE "{db}" WITH (FORCE)')  # dezastrul
    restored = ama_backup.run_op("restore-test", cfg)
    assert restored["stare"] == "reusit", restored["eroare"]
    assert restored["id"] == snap
    assert restored["verificare"]["valoare"] == 1
    assert _scratch_dbs() == "0"  # baza de probă a fost ștearsă
    status = json.loads((tmp / "status" / "ultima-restaurare-test.json").read_text())
    assert status["tip"] == "restaurare_test" and status["stare"] == "reusit" and status["eroare"] is None

    # Fără cheia privată, copia nu se poate citi (cheia de pe server nu este cea a proprietarului)
    out = subprocess.run(
        ["age", "-d", "-i", "/dev/null", str(tmp / "destinatie" / snap / "baza.dump.age")],
        capture_output=True,
        check=False,
    )
    assert out.returncode != 0


def test_copie_corupta_este_raportata_ca_esec(env) -> None:
    cfg, _, tmp = env
    result = ama_backup.run_op("backup", cfg)
    assert result["stare"] == "reusit", result["eroare"]
    victim = tmp / "destinatie" / result["id"] / "baza.dump.age"
    data = bytearray(victim.read_bytes())
    data[len(data) // 2] ^= 0xFF
    victim.write_bytes(bytes(data))

    restored = ama_backup.run_op("restore-test", cfg)
    assert restored["stare"] == "esuat"
    assert "baza.dump.age" in restored["eroare"]
    assert _scratch_dbs() == "0"
    assert json.loads((tmp / "status" / "ultima-restaurare-test.json").read_text())["stare"] == "esuat"


def test_verificare_care_nu_gaseste_datele_esueaza(env) -> None:
    cfg, _, _ = env
    assert ama_backup.run_op("backup", cfg)["stare"] == "reusit"
    cfg.verify_sql = "SELECT count(*) FROM marcaj WHERE text = 'altceva'"
    restored = ama_backup.run_op("restore-test", cfg)
    assert restored["stare"] == "esuat" and "0" in restored["eroare"]


def test_raportare_prin_comanda_externa(env) -> None:
    cfg, _, tmp = env
    sink = tmp / "primit.json"
    cfg.report_cmd = f"tee {sink}"
    result = ama_backup.run_op("backup", cfg)
    assert result["raportare"] == "trimis"
    assert json.loads(sink.read_text())["tip"] == "backup"
    cfg.report_cmd = "/nu/exista"
    assert ama_backup.run_op("backup", cfg)["raportare"].startswith("eroare")  # nu schimbă starea backupului


def test_retentia_sterge_copiile_vechi_de_la_destinatie(env) -> None:
    cfg, _, tmp = env
    dest = tmp / "destinatie"
    for day in range(1, 29):  # 28 de zile consecutive, an trecut
        d = dest / f"202506{day:02d}T030000Z"
        d.mkdir(parents=True)
        (d / "manifest.json").write_text("{}")
    result = ama_backup.run_op("backup", cfg)
    assert result["stare"] == "reusit", result["eroare"]
    left = sorted(p.name for p in dest.iterdir())
    assert result["id"] in left and set(result["retentie"]["sterse"]).isdisjoint(left)
    assert len(left) < 29
