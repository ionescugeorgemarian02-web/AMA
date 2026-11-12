"""F2.2 — cozile din 7.5 și prioritățile P0–P3: partea pură (fără bază)."""

import datetime as dt

import pytest

from app.config import Settings
from app.operare.motor import (
    Coada,
    DefinitieCoada,
    Prioritate,
    calculeaza_prioritate,
    coada_furnizor,
    coada_platforma,
)
from app.operare.motor.cozi import MAX_BIBLIOTECA, definitii_standard

ACUM = dt.datetime(2026, 11, 12, 10, 0, tzinfo=dt.UTC)


def ore(n: float) -> dt.datetime:
    return ACUM + dt.timedelta(hours=n)


# ---- priorități ------------------------------------------------------------------------------------------------------


def test_clasele_se_ordoneaza_oricare_ar_fi_termenul() -> None:
    p0_tarziu = calculeaza_prioritate(Prioritate.P0, ore(10_000))
    p1_devreme = calculeaza_prioritate(Prioritate.P1, ore(-10_000))
    p1_fara = calculeaza_prioritate(Prioritate.P1)
    p2 = calculeaza_prioritate(Prioritate.P2, ore(-1))
    p3 = calculeaza_prioritate(Prioritate.P3, ore(-1))
    assert p0_tarziu < p1_devreme <= p1_fara < p2 < p3


def test_in_aceeasi_clasa_castiga_termenul_cel_mai_apropiat() -> None:
    a, b, c = (calculeaza_prioritate(Prioritate.P1, ore(h)) for h in (1, 2, 30))
    assert a < b < c


def test_fara_termen_vine_dupa_cele_cu_termen_din_aceeasi_clasa() -> None:
    assert calculeaza_prioritate(Prioritate.P2, ore(24 * 365 * 100)) < calculeaza_prioritate(Prioritate.P2)


def test_granulatia_termenului_este_un_minut() -> None:
    assert calculeaza_prioritate(Prioritate.P1, ACUM) == calculeaza_prioritate(
        Prioritate.P1, ACUM + dt.timedelta(seconds=30)
    )
    assert calculeaza_prioritate(Prioritate.P1, ACUM) < calculeaza_prioritate(
        Prioritate.P1, ACUM + dt.timedelta(minutes=1)
    )


@pytest.mark.parametrize("p", list(Prioritate))
@pytest.mark.parametrize("termen", [None, ore(-24 * 365 * 50), ore(24 * 365 * 500), ACUM])
def test_valorile_incap_in_intervalul_bibliotecii(p: Prioritate, termen: dt.datetime | None) -> None:
    assert 1 <= calculeaza_prioritate(p, termen) <= MAX_BIBLIOTECA


def test_termenul_fara_fus_orar_este_refuzat() -> None:
    with pytest.raises(ValueError, match="fus orar"):
        calculeaza_prioritate(Prioritate.P1, dt.datetime(2026, 11, 12, 10, 0))


# ---- definițiile cozilor -------------------------------------------------------------------------------------------------


def test_cozile_standard_urmeaza_tabelul_7_5() -> None:
    d = {c.nume: c for c in definitii_standard(Settings())}
    assert set(d) == {c.value for c in Coada} == {"urgent", "greu", "io", "invatare"}
    assert d["greu"].paralel_global == 2 and d["greu"].paralel_worker == 2, (
        "două culoare, câte un job pe culoar"
    )
    assert d["io"].paralel_global == 24
    assert d["invatare"].paralel_global == 1
    assert d["urgent"].paralel_global is None and d["urgent"].cereri is None, "urgent: fără așteptare"
    assert d["urgent"].polling_sec <= 0.5


def test_numarul_de_culoare_grele_este_configurabil() -> None:
    d = {c.nume: c for c in definitii_standard(Settings(culoare_greu=3, io_paralel=5, invatare_paralel=2))}
    assert (d["greu"].paralel_global, d["io"].paralel_global, d["invatare"].paralel_global) == (3, 5, 2)


def test_culoarele_si_limitele_au_valori_valide() -> None:
    for gresit in ({"culoare_greu": 0}, {"io_paralel": 0}, {"invatare_paralel": 0}):
        with pytest.raises(ValueError, match="greater_than_equal"):
            Settings(**gresit)


def test_fabrica_de_cozi_pe_furnizor_si_pe_platforma() -> None:
    f = coada_furnizor("gemini", cereri=15, perioada_sec=60)
    assert f == DefinitieCoada("furnizor_gemini", cereri=15, perioada_sec=60)
    p = coada_platforma("meta", cereri=200, perioada_sec=3600, paralel=4)
    assert p.nume == "platforma_meta" and p.paralel_global == 4 and p.cereri == 200


@pytest.mark.parametrize("nume", ["", "A", "cu spatiu", "_dbos_x", "x" * 60, "1abc", "cu-liniuta"])
def test_nume_de_coada_nepermise(nume: str) -> None:
    with pytest.raises(ValueError, match="nume de coadă"):
        DefinitieCoada(nume)


def test_limita_de_rata_cere_ambele_valori_pozitive() -> None:
    for kw in (
        {"cereri": 1},
        {"perioada_sec": 1.0},
        {"cereri": 0, "perioada_sec": 1.0},
        {"cereri": 1, "perioada_sec": 0},
    ):
        with pytest.raises(ValueError, match=r"cereri|perioada"):
            DefinitieCoada("x1", **kw)  # type: ignore[arg-type]
