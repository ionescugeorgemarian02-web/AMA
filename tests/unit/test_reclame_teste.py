"""F13.9 — regula câștigătoarei: probabilitate peste 90% și date minime pe fiecare variantă."""

from app.reclame.plan import CriteriiOprire
from app.reclame.teste import decide, probabilitati

C = CriteriiOprire(cost_tinta_bani=4_000)


def test_probabilitatile_insumeaza_unu_si_sunt_deterministe() -> None:
    p = probabilitati([(5_000, 50), (5_000, 20), (5_000, 21)])
    assert abs(sum(p) - 1) < 1e-9 and p == probabilitati([(5_000, 50), (5_000, 20), (5_000, 21)])
    assert p[0] > 0.99


def test_castigatoarea_cere_prag_si_date_minime() -> None:
    i, p, _ = decide([(5_000, 80, 50), (5_000, 80, 20), (5_000, 80, 21)], C)
    assert i == 0 and p[0] > 0.9
    i, _, motiv = decide([(5_000, 80, 50), (500, 8, 0), (5_000, 80, 21)], C)
    assert i is None and "datele minime" in motiv
    i, _, motiv = decide([(5_000, 80, 22), (5_000, 80, 20), (5_000, 80, 21)], C)
    assert i is None and "sub pragul" in motiv
