"""Un test blocat pică repede, cu numele lui în mesaj, nu consumă jobul CI (plafonul din `tests/conftest.py`)."""

import os
import subprocess
import sys

from tests.conftest import ROOT


def test_un_test_blocat_pica_la_plafon_cu_mesaj_clar_iar_urmatorul_ruleaza() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "tests/unit/proba_plafon.py"],
        cwd=ROOT,
        env={**os.environ, "AMA_TEST_PLAFON_SEC": "1"},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    iesire = r.stdout + r.stderr
    assert r.returncode == 1, iesire
    assert "proba_plafon.py::test_blocat a depășit plafonul de 1 s" in iesire
    assert "[PICAT] tests/unit/proba_plafon.py::test_blocat" in iesire  # apare în jurnal pe loc
    assert "1 failed, 1 passed" in iesire  # blocajul nu oprește restul rulării
