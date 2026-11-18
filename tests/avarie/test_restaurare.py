"""F15.3, docs/25 §25.3: restaurarea pe un mediu curat -> platformă funcțională în ținta de timp.

Exercițiul real (`scripts/exercitiu_restaurare.py`): backup criptat al bazei de test migrate (cu un client și
date), mediu curat (bază nouă + director media nou), restaurare, verificare (migrări, rânduri pe fiecare tabel,
RLS, media, `/readyz` ca rolul aplicației) și cronometrare. Uneltele (pg_dump, age, rclone) sunt reale."""

import importlib.util
import shutil
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.conftest import BazaTest

pytestmark = pytest.mark.db
ROOT = Path(__file__).resolve().parents[2]
UNELTE = ("pg_dump", "pg_restore", "psql", "age", "age-keygen", "rclone", "tar")


def _script():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "exercitiu_restaurare", ROOT / "scripts" / "exercitiu_restaurare.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(any(shutil.which(u) is None for u in UNELTE), reason="lipsesc uneltele de backup")
def test_exercitiul_de_restaurare_reface_platforma_in_tinta_de_timp(
    baza: BazaTest, fabrica_clienti: Callable[[], uuid.UUID], tmp_path: Path
) -> None:
    fabrica_clienti()  # un client cu date, ca restaurarea să aibă ce verifica sub RLS
    media = tmp_path / "media"
    (media / "client" / "active").mkdir(parents=True)
    (media / "client" / "active" / "poza.jpg").write_bytes(b"\xff\xd8media-de-proba")
    rez = _script().exercitiu(baza.admin_url, baza.app_url, media=media, lucru=tmp_path / "lucru")
    assert rez["trecut"], rez
    assert all(rez["verificari"].values()) and rez["in_tinta"] and rez["fisiere_media"] == 1
    assert rez["durata_sec"] < 4 * 3600 and set(rez["etape"]) == {
        "backup_sec",
        "restaurare_sec",
        "verificare_sec",
    }
    assert not (tmp_path / "lucru").exists(), "nimic necriptat nu rămâne după exercițiu"


@pytest.mark.skipif(any(shutil.which(u) is None for u in UNELTE), reason="lipsesc uneltele de backup")
def test_exercitiul_peste_tinta_de_timp_nu_trece(baza: BazaTest, tmp_path: Path) -> None:
    rez = _script().exercitiu(baza.admin_url, baza.app_url, tinta_ore=0.0, lucru=tmp_path / "l")
    assert all(rez["verificari"].values()) and not rez["in_tinta"] and not rez["trecut"]
