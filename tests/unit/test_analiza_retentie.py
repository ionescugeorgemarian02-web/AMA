"""F10.2 — nucleele pure ale curbei de retenție: validarea, rezumatul, linia desenată și citirea raportului
YouTube Analytics."""

import pytest

from app.analiza import retentie
from app.analiza.retentie import CurbaRefuzata
from app.connectors.metrici.youtube import puncte_din_raport


def curba(n: int = 100) -> list[tuple[float, float]]:
    """O curbă tipică: pornește de la 1.0, pierde repede la început, apoi coboară lin până la 0.25."""
    out = []
    for i in range(1, n + 1):
        x = i / n
        out.append((x, round(1.0 - 0.4 * min(x, 0.1) / 0.1 - 0.35 * max(0.0, x - 0.1) / 0.9, 4)))
    return out


def test_rezumatul_unei_curbe_tipice() -> None:
    r = retentie.rezumat(curba())
    assert r.dupa_hook == pytest.approx(0.6)
    assert r.la_final == pytest.approx(0.25)
    assert 0.25 < r.medie < 0.6
    assert r.cadere_pozitie <= 0.1 and r.cadere_marime == pytest.approx(0.04, abs=0.001)


def test_caderea_cea_mai_mare_este_gasita_unde_este() -> None:
    p = [(i / 20, 0.9) for i in range(1, 11)] + [(i / 20, 0.4) for i in range(11, 21)]
    r = retentie.rezumat(p)
    assert (r.cadere_pozitie, r.cadere_marime) == (0.55, 0.5)
    plat = retentie.rezumat([(i / 20, 0.5) for i in range(1, 21)])
    assert plat.cadere_marime == 0.0


def test_curbele_fara_forma_sunt_refuzate() -> None:
    with pytest.raises(CurbaRefuzata):
        retentie.valideaza(curba(5))  # prea puține puncte
    with pytest.raises(CurbaRefuzata):
        retentie.valideaza([(i / 10, 0.5) for i in range(1, 12)])  # poziție peste 1
    with pytest.raises(CurbaRefuzata):
        retentie.valideaza([(0.5, 0.5)] * 12)  # poziții repetate
    with pytest.raises(CurbaRefuzata):
        retentie.valideaza([(i / 20, -0.1) for i in range(1, 21)])
    with pytest.raises(CurbaRefuzata):
        retentie.valideaza([(i / 20, 9.0) for i in range(1, 21)])
    amestecata = list(reversed(curba(20)))
    assert retentie.valideaza(amestecata) == curba(20), "ordinea se reface după poziție"


def test_linia_incape_in_grafic_si_se_scaleaza_cand_trece_de_100() -> None:
    linie, varf = retentie.linie_svg(curba(20))
    assert varf == 1.0
    coordonate = [tuple(map(float, c.split(","))) for c in linie.split()]
    assert len(coordonate) == 20
    assert all(0 <= x <= retentie.LATIME and 0 <= y <= retentie.INALTIME for x, y in coordonate)
    assert coordonate[-1] == (retentie.LATIME, retentie.INALTIME * 0.75)
    revazut = [(i / 20, 1.5 if i == 3 else 0.5) for i in range(1, 21)]
    linie2, varf2 = retentie.linie_svg(revazut)
    assert varf2 == 1.5 and "45.0,0.0" in linie2, "pasajul revăzut atinge marginea de sus"


def test_raportul_analytics_se_citeste_dupa_numele_coloanelor() -> None:
    corp = {
        "columnHeaders": [{"name": "audienceWatchRatio"}, {"name": "elapsedVideoTimeRatio"}],
        "rows": [[0.5, 0.02], [0.9, 0.01], ["x", 0.03], [0.4]],
    }
    assert puncte_din_raport(corp) == [(0.01, 0.9), (0.02, 0.5)]
    assert puncte_din_raport({"columnHeaders": [{"name": "views"}], "rows": [[1]]}) == []
    assert puncte_din_raport({}) == []
