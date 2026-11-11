"""F1.9, partea din panou — citirea stării backup-ului din fișierele JSON (contract: docs/specs/F1.9.md)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.operare import backup
from app.operare.backup import Eticheta

ACUM = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def rezultat(
    tip: str = "backup", stare: str = "reusit", inceput: datetime | None = None, **extra: Any
) -> dict[str, Any]:
    inceput = inceput or ACUM - timedelta(hours=2)
    return {
        "schema": "ama.backup/1",
        "tip": tip,
        "stare": stare,
        "mediu": "productie",
        "versiune": "abc123",
        "inceput": inceput.isoformat(),
        "sfarsit": (inceput + timedelta(seconds=12)).isoformat(),
        "durata_s": 12.3,
        "destinatie": "externa:ama",
        "eroare": "pg_dump a căzut" if stare == "esuat" else None,
        "id": inceput.strftime("%Y%m%dT%H%M%SZ"),
        "artefacte": [{"nume": "baza.dump.age", "octeti": 1, "sha256": "0" * 64}],
        "omise": [],
        "retentie": {"pastrate": [], "sterse": []},
        **extra,
    }


def scrie(d: Path, nume: str, continut: dict[str, Any] | str) -> None:
    (d / nume).write_text(continut if isinstance(continut, str) else json.dumps(continut), encoding="utf-8")


def stare(d: Path) -> backup.StareBackup:
    return backup.citeste_stare(d, acum=ACUM)


def test_director_nesetat_este_nerulat_si_nu_pica(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    monkeypatch.delenv("AMA_BACKUP_STATUS_DIR", raising=False)
    get_settings.cache_clear()
    s = backup.citeste_stare(acum=ACUM)
    assert not s.configurat and s.backup.eticheta is Eticheta.NERULAT and not s.bun


def test_director_fara_fisiere_inseamna_inca_nu_a_rulat(tmp_path: Path) -> None:
    s = stare(tmp_path)
    assert s.configurat
    assert s.backup.eticheta is Eticheta.NERULAT and s.restaurare_test.eticheta is Eticheta.NERULAT
    assert backup.citeste_stare(tmp_path / "nu-exista", acum=ACUM).backup.eticheta is Eticheta.NERULAT


def test_totul_proaspat_este_in_regula(tmp_path: Path) -> None:
    scrie(tmp_path, "ultimul-backup.json", rezultat())
    scrie(
        tmp_path, "ultima-restaurare-test.json", rezultat("restaurare_test", inceput=ACUM - timedelta(days=3))
    )
    s = stare(tmp_path)
    assert s.backup.eticheta is Eticheta.OK and s.restaurare_test.eticheta is Eticheta.OK and s.bun
    assert s.backup.ultim is not None and s.backup.ultim.versiune == "abc123"


@pytest.mark.parametrize(
    ("ore", "asteptat"),
    [(25, Eticheta.OK), (26, Eticheta.OK), (27, Eticheta.INVECHIT), (30, Eticheta.INVECHIT)],
)
def test_backup_se_invecheste_dupa_26_de_ore(tmp_path: Path, ore: int, asteptat: Eticheta) -> None:
    scrie(tmp_path, "ultimul-backup.json", rezultat(inceput=ACUM - timedelta(hours=ore)))
    assert stare(tmp_path).backup.eticheta is asteptat


@pytest.mark.parametrize(("zile", "asteptat"), [(7, Eticheta.OK), (8, Eticheta.OK), (9, Eticheta.INVECHIT)])
def test_testul_de_restaurare_se_invecheste_dupa_8_zile(
    tmp_path: Path, zile: int, asteptat: Eticheta
) -> None:
    scrie(
        tmp_path,
        "ultima-restaurare-test.json",
        rezultat("restaurare_test", inceput=ACUM - timedelta(days=zile)),
    )
    assert stare(tmp_path).restaurare_test.eticheta is asteptat


def test_esec_recent_este_rosu_si_ultimul_reusit_vine_din_istoric(tmp_path: Path) -> None:
    reusit = rezultat(inceput=ACUM - timedelta(hours=26))
    scrie(tmp_path, "ultimul-backup.json", rezultat(stare="esuat", inceput=ACUM - timedelta(hours=1)))
    scrie(
        tmp_path,
        "istoric.jsonl",
        json.dumps(reusit) + "\n" + "linie stricată\n" + json.dumps(rezultat("curatare")) + "\n",
    )
    ev = stare(tmp_path).backup
    assert ev.eticheta is Eticheta.ESUAT and ev.detaliu == "pg_dump a căzut"
    assert ev.ultim_reusit is not None and ev.ultim_reusit.id == reusit["id"]


@pytest.mark.parametrize(
    "continut",
    [
        "",
        "{nu e json",
        "[]",
        "null",
        '{"schema": "alta/9", "tip": "backup"}',
        json.dumps({"schema": "ama.backup/1"}),
    ],
)
def test_fisier_corupt_sau_cu_alta_schema_este_necitibil_fara_exceptie(tmp_path: Path, continut: str) -> None:
    scrie(tmp_path, "ultimul-backup.json", continut)
    scrie(tmp_path, "ultima-restaurare-test.json", continut)
    s = stare(tmp_path)
    assert s.backup.eticheta is Eticheta.NECITIBIL and s.restaurare_test.eticheta is Eticheta.NECITIBIL
    assert backup.rezumat(s)


def test_fisier_binar_sau_ilizibil_nu_pica(tmp_path: Path) -> None:
    (tmp_path / "ultimul-backup.json").write_bytes(b"\xff\xfe\x00\x01")
    (tmp_path / "ultima-restaurare-test.json").mkdir()  # nu poate fi citit ca fișier
    s = stare(tmp_path)
    assert s.backup.eticheta is Eticheta.NECITIBIL and s.restaurare_test.eticheta is Eticheta.NECITIBIL


def test_momentul_fara_fus_orar_este_tratat_ca_utc(tmp_path: Path) -> None:
    scrie(
        tmp_path,
        "ultimul-backup.json",
        rezultat(inceput=ACUM - timedelta(hours=1)) | {"inceput": "2026-11-11T11:00:00"},
    )
    assert stare(tmp_path).backup.eticheta is Eticheta.OK


def test_indicatorul_de_sanatate_nu_arunca_si_reflecta_starea(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import get_settings
    from app.operare import health

    monkeypatch.setenv("AMA_BACKUP_STATUS_DIR", str(tmp_path))
    get_settings.cache_clear()
    scrie(tmp_path, "ultimul-backup.json", rezultat(inceput=datetime.now(UTC) - timedelta(days=3)))
    ind = backup.indicator()
    assert not ind.bun and "învechit" not in ind.detaliu and "invechit" in ind.detaliu
    health.register_indicator("rau", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    try:
        rez = health.indicatori()
        assert rez["rau"].bun is False and "RuntimeError" in rez["rau"].detaliu
    finally:
        health._indicatori.pop("rau", None)
    get_settings.cache_clear()
