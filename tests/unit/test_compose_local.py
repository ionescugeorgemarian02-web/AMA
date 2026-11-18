"""Modul local: infra/compose/local.yml e valid, construiește local, publică doar pe 127.0.0.1, conectori simulați."""

import shutil
import subprocess
from pathlib import Path

import pytest

RAD = Path(__file__).resolve().parents[2]
LOCAL = RAD / "infra/compose/local.yml"
EXEMPLU = RAD / "infra/env/local.env.example"


def _compose() -> dict:  # type: ignore[type-arg]
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(LOCAL.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_serviciile_si_volumele() -> None:
    c = _compose()
    assert set(c["services"]) == {"postgres", "migrate", "app", "worker"}
    assert set(c["volumes"]) == {"pgdata", "media"}
    assert "@sha256:" in c["services"]["postgres"]["image"]
    assert "pgvector" in c["services"]["postgres"]["image"]
    for s in ("migrate", "app", "worker"):
        assert c["services"][s]["build"]["dockerfile"] == "Dockerfile"
        assert c["services"][s]["image"].startswith("${")  # construită local, fără registru
    assert c["services"]["app"]["ports"] == ["127.0.0.1:8000:8000"]
    assert "caddy" not in LOCAL.read_text(encoding="utf-8").lower().replace("proxy caddy", "")


def test_conectorii_sunt_simulati_si_cheia_llm_e_optionala() -> None:
    env = _compose()["services"]["worker"]["environment"]
    assert env["AMA_ENV"] == "dev"
    assert env["AMA_PLATI_PROCESATOR"] == env["AMA_EMAIL_FURNIZOR"] == env["AMA_AUDIT_MOTOR"] == "simulat"
    assert env["AMA_PUBLICARE_CONECTORI"] == env["AMA_RECLAME_CONECTORI"] == ""
    assert env["AMA_CHEIE_OPENROUTER"] == "${AMA_CHEIE_OPENROUTER:-}"
    chei = [r.split("=")[0] for r in EXEMPLU.read_text(encoding="utf-8").splitlines() if r and r[0] != "#"]
    assert [k for k in chei if k.startswith("AMA_CHEIE_")] == ["AMA_CHEIE_OPENROUTER"]


def test_garda_de_fixare_trece() -> None:
    r = subprocess.run(
        ["python", str(RAD / "scripts/check_pins.py"), str(RAD)], capture_output=True, text=True, check=False
    )
    assert "local.yml" not in r.stdout, r.stdout


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker lipsește")
def test_docker_compose_config(tmp_path: Path) -> None:
    env = tmp_path / "local.env"
    env.write_text(EXEMPLU.read_text(encoding="utf-8").replace("GENEREAZA_LA_PORNIRE", "x" * 48))
    r = subprocess.run(
        ["docker", "compose", "--env-file", str(env), "-f", str(LOCAL), "config", "-q"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    if "unknown" in r.stderr and "compose" in r.stderr:
        pytest.skip("pluginul docker compose lipsește")
    assert r.returncode == 0, r.stderr
