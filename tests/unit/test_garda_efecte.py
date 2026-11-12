"""F2.5 — garda: conectorii de efecte se cheamă doar din executorul de efecte."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GARDA = ROOT / "scripts" / "check_efecte.py"


def _ruleaza(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GARDA), str(root)], capture_output=True, text=True, check=False
    )


def _fisier(root: Path, rel: str, continut: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(continut)


def test_repo_ul_real_trece() -> None:
    r = _ruleaza(ROOT)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize(
    "linie",
    [
        "from app.connectors.registru import conector_pentru",
        "from app.connectors import registru",
        "import app.connectors.registru",
        "from app.connectors.facebook import Fb",
        "from app.connectors.facebook.api import trimite",
        "x = __import__('app.connectors.facebook')",
        "import importlib\nm = importlib.import_module('app.connectors.registru')",
    ],
)
def test_garda_prinde_apelul_unui_conector_din_afara_executorului(tmp_path: Path, linie: str) -> None:
    _fisier(tmp_path, "app/publicare/api.py", linie + "\n")
    r = _ruleaza(tmp_path)
    assert r.returncode == 1 and "app/publicare/api.py:" in r.stderr and "efecte.cere" in r.stderr


@pytest.mark.parametrize(
    ("cale", "linie"),
    [
        ("app/operare/efecte/executor.py", "from app.connectors import registru"),
        ("app/connectors/facebook/__init__.py", "from app.connectors.registru import inregistreaza"),
        ("tests/conector_fals.py", "from app.connectors.registru import inregistreaza"),
        ("app/publicare/tipuri.py", "from app.connectors.contract import EfectDeTrimis"),
        ("app/panou/web.py", "from app.connectors import telegram"),
        ("app/panou/web2.py", "from app.connectors.telegram import TelegramClient"),
    ],
)
def test_garda_lasa_executorul_conectorii_contractul_si_telegram(
    tmp_path: Path, cale: str, linie: str
) -> None:
    _fisier(tmp_path, cale, linie + "\n")
    r = _ruleaza(tmp_path)
    assert r.returncode == 0, r.stderr
