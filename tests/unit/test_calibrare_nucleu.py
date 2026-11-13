"""F5.8 — nucleul pur al calibrării: eșantionul determinist și stratificat, acordul (procent, kappa, Wilson),
deriva."""

import pytest

from app.validare import calibrare_nucleu as n
from app.validare.calibrare_nucleu import Saptamana


def test_esantionul_este_determinist_si_stratificat_pe_judecator() -> None:
    candidati = [(f"a{i}", "G10@V3") for i in range(50)] + [(f"b{i}", "G9@V4") for i in range(3)]
    e1 = n.esantioneaza(candidati, 5, "2026-W46")
    assert e1 == n.esantioneaza(list(reversed(candidati)), 5, "2026-W46")
    assert sum(i.startswith("a") for i in e1) == 5 and sum(i.startswith("b") for i in e1) == 3
    assert e1 != n.esantioneaza(candidati, 5, "2026-W47"), "altă săptămână, alt eșantion"
    assert n.esantioneaza(candidati, 0, "x") == []


def test_wilson_si_kappa_pe_valori_cunoscute() -> None:
    assert n.wilson(0, 0) is None
    jos, sus = n.wilson(17, 20) or (0, 0)
    assert jos == pytest.approx(0.6396, abs=1e-3) and sus == pytest.approx(0.9476, abs=1e-3)
    assert n.kappa([(True, True), (False, False)] * 5) == 1.0
    assert n.kappa([(True, False), (False, True)] * 5) == -1.0
    assert n.kappa([(True, True)] * 4) is None  # acord întâmplător total: kappa nedefinit
    assert n.kappa([]) is None


def test_acordul_si_alerta_cer_minimum_de_etichete() -> None:
    # judecătorul a blocat 10 și a trecut 12; omul spune că 4 dintre blocaje erau greșite
    etichete = [(True, True)] * 6 + [(True, False)] * 4 + [(False, True)] * 12
    a = n.acord(etichete)
    assert (a.etichete, a.corecte, a.procent) == (22, 18, pytest.approx(0.8182, abs=1e-4))
    assert a.sub_prag and a.interval and a.interval[0] < a.procent < a.interval[1]
    assert a.kappa == pytest.approx(0.6207, abs=1e-3)
    assert not n.acord(etichete[:10]).sub_prag, "sub minimul de etichete nu se alertează"
    assert not n.acord([(True, True)] * 30).sub_prag
    assert n.acord([]).procent is None


def test_deriva_doar_la_aceeasi_versiune() -> None:
    def s(sapt: str, total: int, trecute: int, versiune: str = "1|p@1|m") -> Saptamana:
        return Saptamana("G4@V3", versiune, sapt, total, trecute)

    stabil = [s("2026-W43", 20, 16), s("2026-W44", 20, 17), s("2026-W45", 20, 16)]
    assert n.deriva([*stabil, s("2026-W46", 20, 16)]) == []
    [d] = n.deriva([*stabil, s("2026-W46", 20, 6)])
    assert d.judecator == "G4@V3" and d.saptamana == "2026-W46" and d.diferenta < -0.2
    assert n.deriva([*stabil, s("2026-W46", 20, 6, versiune="1|p@2|m")]) == [], "prompt nou: nu e derivă"
    assert n.deriva([*stabil, s("2026-W46", 5, 0)]) == [], "prea puține verdicte"
