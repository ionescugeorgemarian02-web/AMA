"""F2.7 — partea pură a cozii de erori și autoverificarea watchdog-ului (fără bază)."""

import datetime as dt
import uuid

import pytest

from app.operare.coada_erori import (
    Severitate,
    amprenta_cauzei,
    clasifica,
    grupeaza,
    normalizeaza_mesaj,
)
from app.operare.motor import StareJob
from app.operare.tabele import IntrareEroare
from app.operare.watchdog import COD_IESIRE_FARA_BAZA, Watchdog


def test_mesajul_se_normalizeaza_fara_numere_si_identificatori() -> None:
    a = normalizeaza_mesaj(f"Nu merge jobul {uuid.uuid4()} (cod 42) după 3 încercări")
    b = normalizeaza_mesaj(f"nu MERGE jobul {uuid.uuid4()} (cod 7)  după 9 încercări")
    assert a == b == "nu merge jobul # (cod #) după # încercări"


def test_aceeasi_cauza_are_aceeasi_amprenta_iar_cauze_diferite_amprente_diferite() -> None:
    baza = amprenta_cauzei("f", "p", "EroareDefinitiva", "nu merge 1")
    assert baza == amprenta_cauzei("f", "p", "EroareDefinitiva", "nu merge 22")
    assert len(baza) == 16 and set(baza) <= set("0123456789abcdef")
    for alta in (
        amprenta_cauzei("g", "p", "EroareDefinitiva", "nu merge 1"),
        amprenta_cauzei("f", "q", "EroareDefinitiva", "nu merge 1"),
        amprenta_cauzei("f", None, "EroareDefinitiva", "nu merge 1"),
        amprenta_cauzei("f", "p", "EroareTemporara", "nu merge 1"),
        amprenta_cauzei("f", "p", "EroareDefinitiva", "alt mesaj 1"),
    ):
        assert alta != baza


@pytest.mark.parametrize(
    ("stare", "tip", "asteptat"),
    [
        (StareJob.ESUAT, "EroareDefinitiva", Severitate.MINOR),
        (StareJob.ESUAT, "ValueError", Severitate.MINOR),
        (StareJob.ESUAT, "EroareAutentificare", Severitate.MAJOR),
        (StareJob.EPUIZAT, "Necunoscut", Severitate.MAJOR),
    ],
)
def test_trierea_automata_dupa_22_4(stare: StareJob, tip: str, asteptat: Severitate) -> None:
    assert clasifica(stare, tip) is asteptat


def intrare(cauza: str, severitate: str, ora: int) -> IntrareEroare:
    return IntrareEroare(
        cauza=cauza,
        flux=f"f-{cauza}",
        pas="p",
        eroare_tip="E",
        severitate=severitate,
        creat_la=dt.datetime(2026, 11, 12, ora, tzinfo=dt.UTC),
    )


def test_grupurile_se_ordoneaza_dupa_gravitate_apoi_dupa_noutate() -> None:
    grupuri = grupeaza(
        [
            intrare("aaaa", "minor", 9),
            intrare("aaaa", "minor", 11),
            intrare("bbbb", "major", 8),
            intrare("cccc", "minor", 12),
            intrare("dddd", "critic", 7),
        ]
    )
    assert [g.cauza for g in grupuri] == ["dddd", "bbbb", "cccc", "aaaa"]
    assert grupuri[-1].intrari == 2 and grupuri[-1].ultima.creat_la.hour == 11


def test_un_grup_ia_severitatea_cea_mai_grava_a_intrarilor_lui() -> None:
    (g,) = grupeaza([intrare("aaaa", "minor", 9), intrare("aaaa", "major", 10)])
    assert g.severitate == "major"


# ---- autoverificarea: iese doar dacă nu mai poate dovedi că trăiește -------------------------------------------------


def watchdog(iesiri: list[int], ceas: list[float]) -> Watchdog:
    return Watchdog(
        "w1",
        bataie_sec=1,
        scanare_sec=1,
        timeout_sec=60,
        prag_reporniri=3,
        fereastra_min=60,
        prag_crestere=5,
        iesire=iesiri.append,
        ceas=lambda: ceas[0],
    )


def test_baza_care_nu_raspunde_mai_mult_de_timeout_opreste_procesul(monkeypatch: pytest.MonkeyPatch) -> None:
    iesiri: list[int] = []
    ceas = [1000.0]
    w = watchdog(iesiri, ceas)

    def pica() -> None:
        raise ConnectionError("baza nu răspunde")

    monkeypatch.setattr(w, "bate", pica)
    for t in (1000.0, 1030.0, 1060.0):  # până la timeout nu iese
        ceas[0] = t
        w._bataie_cu_autoverificare()
    assert iesiri == []
    ceas[0] = 1061.0
    w._bataie_cu_autoverificare()
    assert iesiri == [COD_IESIRE_FARA_BAZA]


def test_o_bataie_reusita_reseteaza_numaratoarea(monkeypatch: pytest.MonkeyPatch) -> None:
    iesiri: list[int] = []
    ceas = [0.0]
    w = watchdog(iesiri, ceas)
    raspunsuri = iter([False, True, False])

    def bate() -> None:
        if not next(raspunsuri):
            raise ConnectionError

    monkeypatch.setattr(w, "bate", bate)
    ceas[0] = 0
    w._bataie_cu_autoverificare()  # eșec la t=0
    ceas[0] = 50
    w._bataie_cu_autoverificare()  # reușită la t=50: numărătoarea se oprește
    ceas[0] = 100
    w._bataie_cu_autoverificare()  # eșec nou la t=100: abia acum începe
    ceas[0] = 150
    monkeypatch.setattr(w, "bate", lambda: (_ for _ in ()).throw(ConnectionError()))
    w._bataie_cu_autoverificare()
    assert iesiri == [], "50 de secunde de la ultimul eșec nou: sub timeout"
