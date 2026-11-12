"""F3.3 — nucleul pur al limitatoarelor: ferestre, plafoane cu rezerva de 10% pentru P0, estimarea tokenilor."""

import datetime as dt
import itertools

import pytest

from app.gateway import cote
from app.gateway.cote import Fereastra
from app.operare.motor import Prioritate

UTC = dt.UTC


def moment(h: int, m: int, s: int = 0, zi: int = 12) -> dt.datetime:
    return dt.datetime(2026, 11, zi, h, m, s, 500_000, tzinfo=UTC)


def test_fereastra_de_minut() -> None:
    t = moment(12, 34, 56)
    assert cote.inceput_fereastra(t, Fereastra.MINUT) == dt.datetime(2026, 11, 12, 12, 34, tzinfo=UTC)
    assert cote.sfarsit_fereastra(t, Fereastra.MINUT) == dt.datetime(2026, 11, 12, 12, 35, tzinfo=UTC)


def test_fereastra_zilnica_cu_ora_de_resetare() -> None:
    assert cote.inceput_fereastra(moment(12, 0), Fereastra.ZI) == dt.datetime(2026, 11, 12, tzinfo=UTC)
    assert cote.sfarsit_fereastra(moment(23, 59), Fereastra.ZI) == dt.datetime(2026, 11, 13, tzinfo=UTC)
    # resetare la 03:00 UTC: înainte de oră, ziua curentă a început ieri la 03:00
    assert cote.inceput_fereastra(moment(2, 59), Fereastra.ZI, 3) == dt.datetime(2026, 11, 11, 3, tzinfo=UTC)
    assert cote.inceput_fereastra(moment(3, 0), Fereastra.ZI, 3) == dt.datetime(2026, 11, 12, 3, tzinfo=UTC)
    assert cote.sfarsit_fereastra(moment(2, 59), Fereastra.ZI, 3) == dt.datetime(2026, 11, 12, 3, tzinfo=UTC)


def test_fusuri_orare_se_aduc_la_utc() -> None:
    bucuresti = dt.timezone(dt.timedelta(hours=2))
    t = dt.datetime(2026, 11, 12, 1, 30, tzinfo=bucuresti)  # 23:30 UTC în 11 noiembrie
    assert cote.inceput_fereastra(t, Fereastra.ZI) == dt.datetime(2026, 11, 11, tzinfo=UTC)


def test_reluarea_vine_la_putin_timp_dupa_resetare() -> None:
    sfarsit = dt.datetime(2026, 11, 12, 12, 35, tzinfo=UTC)
    assert cote.reluare_dupa(sfarsit) == sfarsit + dt.timedelta(seconds=cote.MARJA_RESET_SEC)


@pytest.mark.parametrize("prioritate", list(Prioritate))
def test_pe_minut_nu_exista_rezerva(prioritate: Prioritate) -> None:
    assert cote.plafon(20, Fereastra.MINUT, prioritate) == 20


def test_rezerva_de_10_la_suta_din_limita_zilnica_este_a_lui_p0() -> None:
    assert cote.plafon(1000, Fereastra.ZI, Prioritate.P0) == 1000
    for p in (Prioritate.P1, Prioritate.P2, Prioritate.P3):
        assert cote.plafon(1000, Fereastra.ZI, p) == 900
    assert cote.plafon(50, Fereastra.ZI, Prioritate.P1) == 45
    assert cote.plafon(5, Fereastra.ZI, Prioritate.P2) == 4  # se rotunjește în jos: rezerva nu se micșorează
    assert cote.plafon(None, Fereastra.ZI, Prioritate.P1) is None


def test_estimarea_tokenilor() -> None:
    assert cote.estimeaza_tokeni(0, 100) == 100
    assert cote.estimeaza_tokeni(300, 100) == 200
    assert cote.estimeaza_tokeni(301, 0) == 101  # rotunjit în sus: estimarea nu rămâne sub realitate


def test_permite_este_conditia_aplicata_in_baza() -> None:
    # (folosite, plafon, ceruți) pe axe independente; None = fără plafon
    for folosite, plafon_c in itertools.product(range(0, 4), [None, 0, 1, 2, 3]):
        asteptat = plafon_c is None or folosite + 1 <= plafon_c
        assert cote.permite(folosite, 0, 0, plafon_c, None) is asteptat
    for tokeni_f, ceruti, plafon_t in itertools.product(range(0, 300, 100), [0, 50, 150], [None, 100, 250]):
        asteptat = plafon_t is None or tokeni_f + ceruti <= plafon_t
        assert cote.permite(0, tokeni_f, ceruti, None, plafon_t) is asteptat


def test_pauza_dupa_429() -> None:
    t = moment(12, 0)
    assert cote.pana_la_dupa_429(7, t) == t + dt.timedelta(seconds=7)
    assert cote.pana_la_dupa_429(None, t) == t + dt.timedelta(seconds=60)
    assert cote.pana_la_dupa_429(-3, t) == t


def test_limitele_se_citesc_pe_fereastra() -> None:
    lim = cote.LimiteCota(cereri_minut=1, cereri_zi=2, tokeni_minut=3, tokeni_zi=4)
    assert lim.pe(Fereastra.MINUT) == (1, 3) and lim.pe(Fereastra.ZI) == (2, 4)
    assert cote.LimiteCota().goala and not lim.goala
