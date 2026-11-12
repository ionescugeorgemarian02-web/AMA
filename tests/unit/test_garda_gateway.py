"""F3.2 — garda gateway-ului: apelurile la modele trec doar prin `app/gateway` (și fără SDK-uri)."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GARDA = ROOT / "scripts" / "check_gateway.py"


def _ruleaza(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GARDA), str(root)], capture_output=True, text=True, check=False
    )


def _fisier(root: Path, rel: str, continut: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(continut)


def _gateway_minimal(root: Path) -> None:
    _fisier(root, "app/gateway/__init__.py", '__all__ = ["apeleaza", "registru"]\n')
    _fisier(root, "app/gateway/client.py", "")
    _fisier(root, "app/gateway/registru.py", "")
    _fisier(root, "app/gateway/adaptoare/__init__.py", "")


def test_repo_ul_real_trece() -> None:
    r = _ruleaza(ROOT)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize(
    "linie",
    [
        "from app.gateway.client import trimite",
        "from app.gateway.adaptoare import adaptor_pentru",
        "import app.gateway.adaptoare.openai_compat",
        "from app.gateway import client",
        "from app.gateway import registru, adaptoare",
        "from app import gateway\ngateway.client.trimite()",
        "import importlib\nm = importlib.import_module('app.gateway.client')",
    ],
)
def test_garda_prinde_importul_intern_din_afara_gateway_ului(tmp_path: Path, linie: str) -> None:
    _gateway_minimal(tmp_path)
    _fisier(tmp_path, "app/creier/ruta.py", linie + "\n")
    r = _ruleaza(tmp_path)
    assert r.returncode == 1 and "app/creier/ruta.py:" in r.stderr and "intern" in r.stderr


@pytest.mark.parametrize(
    "linie",
    [
        'URL = "https://api.anthropic.com/v1/messages"',
        'u = "https://openrouter.ai/api/v1/chat/completions"',
        'host = "generativelanguage.googleapis.com"',
        'x = f"https://API.GROQ.COM/{cale}"',
    ],
)
def test_garda_prinde_adresele_de_furnizori_din_afara_gateway_ului(tmp_path: Path, linie: str) -> None:
    _fisier(tmp_path, "app/cercetare/sursa.py", linie + "\n")
    r = _ruleaza(tmp_path)
    assert r.returncode == 1 and "app/cercetare/sursa.py:" in r.stderr and "gateway" in r.stderr


@pytest.mark.parametrize(
    "linie",
    [
        "import openai",
        "from anthropic import Anthropic",
        "import google.generativeai as genai",
        "import litellm",
    ],
)
def test_garda_interzice_sdk_urile_oriunde(tmp_path: Path, linie: str) -> None:
    for rel in ("app/cercetare/sursa.py", "app/gateway/client.py", "tests/unit/test_x.py"):
        _fisier(tmp_path, rel, linie + "\n")
    r = _ruleaza(tmp_path)
    assert r.returncode == 1 and r.stderr.count("SDK de furnizor") == 3


def test_garda_lasa_gateway_ul_si_testele_sa_foloseasca_ce_le_trebuie(tmp_path: Path) -> None:
    _gateway_minimal(tmp_path)
    _fisier(tmp_path, "app/gateway/inventar.py", 'URL = "https://api.groq.com/openai/v1"\n')
    _fisier(tmp_path, "app/gateway/apel.py", "from app.gateway.client import trimite\n")
    _fisier(
        tmp_path,
        "tests/contract/test_x.py",
        'from app.gateway.client import trimite\nU = "https://api.groq.com"\n',
    )
    _fisier(
        tmp_path,
        "app/creier/ok.py",
        "from app import gateway\nfrom app.gateway import registru, apeleaza\ngateway.registru.x()\n",
    )
    r = _ruleaza(tmp_path)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize(
    "linie",
    ["eval(x)", "exec(x)", "import subprocess", "from subprocess import run", "import os\nos.system('ls')"],
)
def test_gateway_ul_nu_executa_nimic_din_ce_spune_un_model(tmp_path: Path, linie: str) -> None:
    _gateway_minimal(tmp_path)
    _fisier(tmp_path, "app/gateway/rau.py", linie + "\n")
    r = _ruleaza(tmp_path)
    assert r.returncode == 1 and "ieșirea unui model nu se execută" in r.stderr
