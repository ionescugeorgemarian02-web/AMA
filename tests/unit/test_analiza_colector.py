"""F10.1 — nucleele pure ale colectorului de metrici: ce interval e deschis, ce a fost ratat, ce cifre se
acceptă."""

import datetime as dt

import pytest

from app.analiza import colector
from app.analiza.colector import MetriciRefuzate, planifica
from app.connectors.contract import CHEI_METRICI, ETICHETE_METRICI, Metrici

T0 = dt.datetime(2026, 11, 1, 9, 0, tzinfo=dt.UTC)
H = dt.timedelta(hours=1)
Z = dt.timedelta(days=1)


def test_intervalele_sunt_cele_din_7_2() -> None:
    assert [c for c, _ in colector.INTERVALE] == ["1h", "24h", "72h", "7z", "28z"]
    assert [m for _, m in colector.INTERVALE] == [H, 24 * H, 72 * H, 7 * Z, 28 * Z]
    assert set(colector.ETICHETE_INTERVAL) == {c for c, _ in colector.INTERVALE}


@pytest.mark.parametrize(
    ("dupa", "existente", "de_citit", "ratate"),
    [
        (59 * dt.timedelta(minutes=1), set(), None, ()),  # înainte de prima oră: nimic
        (H, set(), "1h", ()),
        (H + 9 * dt.timedelta(minutes=1), set(), "1h", ()),
        (23 * H, {"1h"}, None, ()),  # citit deja; următorul nu e scadent
        (24 * H, {"1h"}, "24h", ()),
        (25 * H, set(), "24h", ("1h",)),  # colectorul a lipsit o zi: ora 1 e ratată, nu „recuperată”
        (8 * Z, {"1h", "24h"}, "7z", ("72h",)),
        (28 * Z + 6 * Z, {"1h", "24h", "72h", "7z"}, "28z", ()),  # ultimul interval are o săptămână de grație
        (28 * Z + 7 * Z, {"1h", "24h", "72h", "7z"}, None, ("28z",)),
        (40 * Z, set(), None, ("1h", "24h", "72h", "7z", "28z")),
        (30 * Z, {"1h", "24h", "72h", "7z", "28z"}, None, ()),
    ],
)
def test_planul_unei_postari(
    dupa: dt.timedelta, existente: set[str], de_citit: str | None, ratate: tuple[str, ...]
) -> None:
    p = planifica(T0, existente, T0 + dupa)
    assert (p.de_citit, p.ratate) == (de_citit, ratate)


def test_intarzierea_se_masoara_de_la_momentul_intervalului() -> None:
    assert planifica(T0, set(), T0 + H + dt.timedelta(minutes=7)).intarziere == dt.timedelta(minutes=7)
    assert planifica(T0, {"1h"}, T0 + 30 * H).intarziere == 6 * H


def test_cifrele_acceptate_sunt_intregi_nenegativi_cu_chei_cunoscute() -> None:
    assert colector.curata({"afisari": 120, "aprecieri": 0}) == {"afisari": 120, "aprecieri": 0}
    for gresit in ({"afisari": -1}, {"afisari": 1.5}, {"afisari": "12"}, {"afisari": True}, {"inventata": 3}):
        with pytest.raises(MetriciRefuzate):
            colector.curata(gresit)


def test_o_cifra_lipsa_nu_devine_zero() -> None:
    m = Metrici(aprecieri=4, comentarii=0)
    assert m.ca_dict() == {"aprecieri": 4, "comentarii": 0}
    assert "afisari" not in m.ca_dict()
    assert Metrici().goale and not m.goale
    assert set(ETICHETE_METRICI) == set(CHEI_METRICI)
