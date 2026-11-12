"""F3.8 — nucleul pur al bugetelor: plafoane pe prioritate, depășiri, prag, ferestre."""

import datetime as dt
from decimal import Decimal

import pytest

from app.gateway.reguli_buget import (
    Axa,
    Consum,
    Fereastra,
    Valori,
    axe_la_prag,
    depasiri,
    inceput_fereastra,
    permite,
    plafon,
    raport,
    sfarsit_fereastra,
)
from app.operare.motor import Prioritate

BUGET = Valori(apeluri=10, tokeni=1000, pret_umbra=Decimal("2.00"))


def test_p0_nu_are_plafon_p1_are_plafon_majorat_iar_p2_p3_au_bugetul() -> None:
    assert plafon(BUGET, Prioritate.P0, 1.5) == Valori()
    assert plafon(BUGET, Prioritate.P1, 1.5) == Valori(15, 1500, Decimal("3.00"))
    assert plafon(BUGET, Prioritate.P2, 1.5) == BUGET
    assert plafon(BUGET, Prioritate.P3, 1.5) == BUGET
    # axele fără buget rămân fără limită, la orice prioritate
    assert plafon(Valori(apeluri=4), Prioritate.P1, 1.5) == Valori(6, None, None)


def test_permite_numara_un_apel_nou_si_cere_tokeni_si_pret_sub_plafon() -> None:
    assert permite(Consum(9, 999, Decimal("1.99")), BUGET)  # al 10-lea apel încape
    assert not permite(Consum(10, 0, Decimal(0)), BUGET)  # al 11-lea nu
    assert not permite(Consum(0, 1000, Decimal(0)), BUGET)  # tokenii atinși
    assert not permite(Consum(0, 0, Decimal("2.00")), BUGET)  # prețul atins
    assert permite(Consum(10**9, 10**9, Decimal(10**9)), Valori())  # fără limită


def test_bugetul_zero_refuza_de_la_primul_apel() -> None:
    assert not permite(Consum(), Valori(apeluri=0))
    assert not permite(Consum(), Valori(tokeni=0))
    assert depasiri(Consum(), Valori(apeluri=0, tokeni=0)) == [Axa.APELURI, Axa.TOKENI]


def test_raportul_si_pragul_de_avertizare() -> None:
    consum = Consum(8, 100, Decimal("0.10"))
    assert raport(consum, BUGET, Axa.APELURI) == pytest.approx(0.8)
    assert raport(consum, Valori(), Axa.APELURI) is None
    assert axe_la_prag(consum, BUGET, 0.8) == [Axa.APELURI]
    assert axe_la_prag(Consum(7, 100, Decimal(0)), BUGET, 0.8) == []
    assert raport(Consum(1), Valori(apeluri=0), Axa.APELURI) == 1.0


def test_ferestrele_zi_si_luna_cu_ora_de_resetare() -> None:
    t = dt.datetime(2026, 11, 12, 12, 0, 10, tzinfo=dt.UTC)
    assert inceput_fereastra(t, Fereastra.ZI) == dt.datetime(2026, 11, 12, tzinfo=dt.UTC)
    assert sfarsit_fereastra(t, Fereastra.ZI) == dt.datetime(2026, 11, 13, tzinfo=dt.UTC)
    assert inceput_fereastra(t, Fereastra.LUNA) == dt.datetime(2026, 11, 1, tzinfo=dt.UTC)
    assert sfarsit_fereastra(t, Fereastra.LUNA) == dt.datetime(2026, 12, 1, tzinfo=dt.UTC)
    # înainte de ora de resetare încă e ziua (și luna) de ieri
    devreme = dt.datetime(2026, 12, 1, 2, 0, tzinfo=dt.UTC)
    assert inceput_fereastra(devreme, Fereastra.ZI, 4) == dt.datetime(2026, 11, 30, 4, tzinfo=dt.UTC)
    assert inceput_fereastra(devreme, Fereastra.LUNA, 4) == dt.datetime(2026, 11, 1, 4, tzinfo=dt.UTC)
    # trecerea dintre ani
    ian = dt.datetime(2027, 1, 1, 1, 0, tzinfo=dt.UTC)
    assert inceput_fereastra(ian, Fereastra.LUNA, 4) == dt.datetime(2026, 12, 1, 4, tzinfo=dt.UTC)
    assert sfarsit_fereastra(dt.datetime(2026, 12, 15, tzinfo=dt.UTC), Fereastra.LUNA) == dt.datetime(
        2027, 1, 1, tzinfo=dt.UTC
    )
