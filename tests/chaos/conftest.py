from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.chaos.utile import Worker
from tests.conftest import BazaTest


@pytest.fixture
def dir_proba(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Directorul de coordonare cu fluxurile de probă (și pentru codul din procesul testului)."""
    monkeypatch.setenv("AMA_PROBA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def workeri(baza: BazaTest, dir_proba: Path, motor_curat: None) -> Iterator[list[Worker]]:
    """Lista workerilor porniți de test; toți sunt opriți la final, orice ar fi ieșit."""
    lista: list[Worker] = []
    yield lista
    for w in lista:
        w.curata()


# Clienți și utilizatori pentru testele cu livrabile (F2.5+).
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: E402, F401
