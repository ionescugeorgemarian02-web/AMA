"""F1.9 — retenția (7 zilnice / 4 săptămânale / 6 lunare), programarea și verificarea manifestului."""

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "infra" / "backup" / "ama_backup.py"
spec = importlib.util.spec_from_file_location("ama_backup_unit", PATH)
assert spec and spec.loader
b = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = b
spec.loader.exec_module(b)


def ids(start: datetime, days: int, hour: int = 3) -> list[str]:
    return [
        b.new_snapshot_id((start + timedelta(days=i)).replace(hour=hour, minute=0, second=0))
        for i in range(days)
    ]


def test_retentia_pastreaza_7_zilnice_4_saptamanale_6_lunare() -> None:
    all_ids = ids(datetime(2025, 1, 1, tzinfo=UTC), 400)  # o copie pe zi, 400 de zile
    keep, delete = b.plan_retention(all_ids)
    assert set(keep) | set(delete) == set(all_ids) and not set(keep) & set(delete)

    # calcul independent: cea mai nouă copie din fiecare găleată, ultimele n găleți
    def expected(bucket, n):
        best = {}
        for i in sorted(all_ids):
            best[bucket(b.snapshot_time(i))] = i
        return {best[k] for k in sorted(best)[-n:]}

    want = (
        expected(lambda t: t.date(), 7)
        | expected(lambda t: t.isocalendar()[:2], 4)
        | expected(lambda t: (t.year, t.month), 6)
    )
    assert set(keep) == want
    assert max(keep) == max(all_ids) and len(keep) < 17


def test_retentia_alege_cea_mai_noua_copie_din_fiecare_zi_saptamana_luna() -> None:
    day = ["20260110T030000Z", "20260110T150000Z"]
    keep, delete = b.plan_retention(day, daily=1, weekly=0, monthly=0)
    assert keep == ["20260110T150000Z"] and delete == ["20260110T030000Z"]


def test_retentia_nu_atinge_nume_straine_si_ignora_duplicatele() -> None:
    keep, delete = b.plan_retention(["20260110T030000Z", "20260110T030000Z", "gunoi", "latest"])
    assert keep == ["20260110T030000Z"] and delete == []


def test_retentia_pe_liste_mici_si_goale() -> None:
    assert b.plan_retention([]) == ([], [])
    one = ["20260110T030000Z"]
    assert b.plan_retention(one) == (one, [])


def test_retentia_cu_goluri_numara_zilele_cu_copii_nu_zilele_calendaristice() -> None:
    sparse = ["20260101T030000Z", "20260201T030000Z", "20260301T030000Z"]
    keep, delete = b.plan_retention(sparse, daily=2, weekly=0, monthly=0)
    assert keep == ["20260201T030000Z", "20260301T030000Z"] and delete == ["20260101T030000Z"]


def test_programarea_backupului_zilnic() -> None:
    at = lambda h, m=0: datetime(2026, 3, 4, h, m, tzinfo=UTC)  # noqa: E731 - miercuri
    assert b.due_jobs(at(2, 59), None, None) == []  # înainte de oră
    assert b.due_jobs(at(3, 0), None, None) == ["backup"]
    assert b.due_jobs(at(9), at(3, 1), None) == []  # copia de azi există
    assert b.due_jobs(at(9), datetime(2026, 3, 3, 3, 1, tzinfo=UTC), None) == [
        "backup"
    ]  # lipsește cea de azi


def test_testul_de_restaurare_ruleaza_o_data_pe_saptamana_dupa_backup() -> None:
    sunday = datetime(2026, 3, 8, tzinfo=UTC)
    backup_done = sunday.replace(hour=3, minute=5)
    assert b.due_jobs(sunday.replace(hour=3, minute=10), backup_done, None) == []  # prea devreme
    assert b.due_jobs(sunday.replace(hour=3, minute=40), backup_done, None) == ["restore-test"]
    assert b.due_jobs(sunday.replace(hour=5), backup_done, sunday.replace(hour=4)) == []  # deja făcut azi
    last_week = datetime(2026, 3, 1, 4, tzinfo=UTC)
    assert b.due_jobs(sunday.replace(hour=5), backup_done, last_week) == ["restore-test"]
    monday = datetime(2026, 3, 9, 12, tzinfo=UTC)
    assert b.due_jobs(monday, monday.replace(hour=3, minute=5), None) == []  # nu e ziua săptămânală


def test_adrese_postgres() -> None:
    assert b.libpq_url("postgresql+psycopg://u:p@h:5432/x") == "postgresql://u:p@h:5432/x"
    assert b.libpq_url("postgresql://u@h/x") == "postgresql://u@h/x"
    assert b.with_database("postgresql+psycopg://u@h:1/postgres", "t1") == "postgresql://u@h:1/t1"
    assert (
        b.with_database("postgresql://u@h/postgres?sslmode=require", "t1")
        == "postgresql://u@h/t1?sslmode=require"
    )


def test_manifestul_detecteaza_lipsa_mărimea_si_suma() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "a.age").write_bytes(b"continut")
        art = {"nume": "a.age", "octeti": 8, "sha256": hashlib.sha256(b"continut").hexdigest()}
        assert b.verify_manifest({"artefacte": [art]}, d) == []
        (d / "a.age").write_bytes(b"continuT")
        assert "SHA-256" in b.verify_manifest({"artefacte": [art]}, d)[0]
        (d / "a.age").write_bytes(b"scurt")
        assert "mărime" in b.verify_manifest({"artefacte": [art]}, d)[0]
        (d / "a.age").unlink()
        assert "lipsește" in b.verify_manifest({"artefacte": [art]}, d)[0]
        assert b.verify_manifest({"artefacte": []}, d)


def test_configurarea_citeste_mediul_si_cere_variabilele_obligatorii() -> None:
    import pytest

    with pytest.raises(b.BackupError):
        b.Config.from_env({})
    cfg = b.Config.from_env(
        {
            "AMA_BACKUP_DATABASE_URL": "postgresql+psycopg://u@h/x",
            "AMA_BACKUP_DEST": "ext:bucket/ama/",
            "AMA_BACKUP_AGE_RECIPIENTS": "age1aaa, age1bbb",
            "AMA_BACKUP_CONFIG_PATHS": "/a:/b",
        }
    )
    assert cfg.database_url == "postgresql://u@h/x" and cfg.dest == "ext:bucket/ama"
    assert cfg.recipients == ["age1aaa", "age1bbb"] and cfg.config_paths == [Path("/a"), Path("/b")]
    assert json.loads(json.dumps(b.SCHEMA)) == "ama.backup/1"
