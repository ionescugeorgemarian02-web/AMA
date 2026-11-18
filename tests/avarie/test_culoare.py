"""F15.1, docs/25 §25.3: toate culoarele grele sunt ocupate și sosește un job P0 -> trece în fața cozii și
pornește la primul culoar eliberat."""

import datetime as dt
from collections.abc import Callable, Iterator

import pytest

from app.operare import motor
from app.operare.motor import Coada, Prioritate
from tests.integration import fluxuri_cozi as cozi

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _curat(porneste_executor: Callable[..., None]) -> Iterator[None]:
    cozi.reseteaza()
    yield
    cozi.elibereaza_tot()
    cozi.reseteaza()


def _trimite(nume: str, **kw: object) -> str:
    cozi.blocheaza(nume)
    return motor.trimite(cozi.job, nume, coada=Coada.GREU, cheie=f"avarie-{nume}", **kw)  # type: ignore[arg-type]


def test_p0_trece_in_fata_cozii_cand_culoarele_grele_sunt_ocupate(
    porneste_executor: Callable[..., None],
) -> None:
    porneste_executor(culoare_greu=2)
    ids = [_trimite("ocupat1", prioritate=Prioritate.P2), _trimite("ocupat2", prioritate=Prioritate.P2)]
    cozi.asteapta_pornirea("ocupat1")
    cozi.asteapta_pornirea("ocupat2")
    ids += [_trimite(f"asteapta{i}", prioritate=Prioritate.P1) for i in range(3)]
    ids.append(
        _trimite("p0", prioritate=Prioritate.P0, termen=dt.datetime.now(dt.UTC) + dt.timedelta(hours=2))
    )
    assert not cozi.a_pornit("p0"), "culoarele sunt ocupate: P0 așteaptă, nu sare peste limită"
    cozi.elibereaza("ocupat1")  # primul culoar eliberat
    cozi.asteapta_pornirea("p0")
    assert cozi.pornite()[2] == "p0", cozi.pornite()  # înaintea celor trei P1 sosiți mai devreme
    cozi.elibereaza_tot()
    for i in ids:
        assert motor.asteapta_flux(i, timeout_sec=20).stare is motor.StareJob.TERMINAT
