"""F2.1 — biblioteca de workflow-uri se importă într-un singur loc (`app/operare/motor/`)."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GARDA = ROOT / "scripts" / "check_motor.py"


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
        "import dbos",
        "import dbos.cli",
        "from dbos import DBOS",
        "from dbos._core import StepOptions",
        "import dbos as d",
        "x = __import__('dbos')",
        "import importlib\nm = importlib.import_module('dbos._client')",
    ],
)
def test_importul_in_afara_motorului_pica(tmp_path: Path, linie: str) -> None:
    _fisier(tmp_path, "app/cercetare/ceva.py", linie + "\n")
    r = _ruleaza(tmp_path)
    assert r.returncode == 1 and "app/cercetare/ceva.py" in r.stderr


def test_nici_testele_si_scripturile_nu_au_voie(tmp_path: Path) -> None:
    _fisier(tmp_path, "tests/unit/test_x.py", "from dbos import DBOS\n")
    _fisier(tmp_path, "scripts/y.py", "import dbos\n")
    r = _ruleaza(tmp_path)
    assert r.returncode == 1 and "tests/unit/test_x.py" in r.stderr and "scripts/y.py" in r.stderr


def test_in_modulul_motorului_este_permis(tmp_path: Path) -> None:
    _fisier(tmp_path, "app/operare/motor/executie.py", "from dbos import DBOS\nimport dbos\n")
    assert _ruleaza(tmp_path).returncode == 0


def test_mentiunile_in_text_si_alte_pachete_nu_pica(tmp_path: Path) -> None:
    _fisier(
        tmp_path,
        "app/a.py",
        '"""Folosim dbos prin motor."""\nTEXT = "import dbos"\nimport dbosish\nfrom mydbos import x\n',
    )
    assert _ruleaza(tmp_path).returncode == 0
