"""F1.2 — CI pică la o dependență nefixată și la un secret de probă."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINS = ROOT / "scripts" / "check_pins.py"


def _pins(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(PINS), str(root)], capture_output=True, text=True, check=False)


def _repo(tmp_path: Path, dep: str = "fastapi==1.0.0") -> Path:
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname="x"\nversion="0"\ndependencies=["{dep}"]\n')
    (tmp_path / "uv.lock").write_text(
        'version = 1\n[[package]]\nname = "fastapi"\nversion = "1.0.0"\n'
        'wheels = [{ url = "https://x/f.whl", hash = "sha256:abc" }]\n'
    )
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    return tmp_path


def test_repo_ul_real_trece() -> None:
    r = _pins(ROOT)
    assert r.returncode == 0, r.stdout


def test_dependenta_nefixata_pica(tmp_path: Path) -> None:
    for dep in ("fastapi>=1.0", "fastapi", "fastapi~=1.0", "fastapi==1.*,>0"):
        r = _pins(_mk(tmp_path, dep))
        assert r.returncode == 1, dep
        assert "nefixată" in r.stdout


def _mk(tmp_path: Path, dep: str) -> Path:
    d = tmp_path / str(abs(hash(dep)))
    d.mkdir()
    return _repo(d, dep)


def test_dependenta_fixata_trece(tmp_path: Path) -> None:
    assert _pins(_repo(tmp_path)).returncode == 0


def test_pachet_fara_hash_pica(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "uv.lock").write_text('version = 1\n[[package]]\nname = "fastapi"\nversion = "1.0.0"\n')
    r = _pins(root)
    assert r.returncode == 1 and "fără hash" in r.stdout


def test_imagine_fara_amprenta_pica(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "Dockerfile").write_text("FROM python:3.13-slim AS build\nFROM build\n")
    r = _pins(root)
    assert r.returncode == 1 and "amprentă" in r.stdout
    (root / "Dockerfile").write_text("FROM python:3.13-slim@sha256:" + "a" * 64 + " AS build\nFROM build\n")
    assert _pins(root).returncode == 0


def test_actiune_pe_eticheta_pica(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    wf = root / ".github" / "workflows" / "ci.yml"
    wf.write_text("jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n")
    r = _pins(root)
    assert r.returncode == 1 and "SHA" in r.stdout
    wf.write_text("jobs:\n  a:\n    steps:\n      - uses: actions/checkout@" + "b" * 40 + " # v4\n")
    assert _pins(root).returncode == 0


def test_secret_de_proba_este_prins(tmp_path: Path) -> None:
    # Cheia este construită la rulare, ca fișierul de test să nu conțină el însuși un secret.
    fake = "AKIA" + "IOSFODNN7" + "EXAMPLE"
    f = tmp_path / "config.py"
    f.write_text(f'AWS_ACCESS_KEY_ID = "{fake}"\n')
    baseline = tmp_path / "baseline.json"
    scan = subprocess.run(
        [sys.executable, "-m", "detect_secrets", "scan", "--string", fake],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "True" in scan.stdout
    baseline.write_text(
        subprocess.run(
            [sys.executable, "-m", "detect_secrets", "scan", str(tmp_path / "gol")],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    hook = subprocess.run(
        [sys.executable, "-m", "detect_secrets.pre_commit_hook", "--baseline", str(baseline), str(f)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert hook.returncode != 0
