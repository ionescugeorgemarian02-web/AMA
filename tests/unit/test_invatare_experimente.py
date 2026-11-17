"""F11.4 — regula de oprire a unui experiment (nucleu pur)."""

from app.invatare.experimente import ETICHETE_CONCLUZIE, verdict

BUN = [0.08, 0.09, 0.07, 0.10, 0.08, 0.09, 0.08, 0.09, 0.10, 0.07]
SLAB = [0.03, 0.02, 0.04, 0.03, 0.02, 0.03, 0.04, 0.03, 0.02, 0.03]


def test_experimentul_continua_pana_la_minimul_declarat() -> None:
    c, cifre = verdict(BUN[:4], SLAB, minim=10, prag=0.2, expirat=False)
    assert c is None and (cifre["n_a"], cifre["n_b"]) == (4, 10)
    assert verdict(BUN[:4], SLAB, minim=10, prag=0.2, expirat=True)[0] == "neconcludent", (
        "la termen, din date puține nu se trage o concluzie"
    )
    assert verdict([], [], minim=2, prag=0.2, expirat=False) == (
        None,
        {"n_a": 0, "n_b": 0, "medie_a": None, "medie_b": None},
    )


def test_castiga_varianta_mai_buna_doar_cu_diferenta_clara() -> None:
    c, cifre = verdict(BUN, SLAB, minim=10, prag=0.2, expirat=False)
    assert c == "castiga_a" and cifre["z"] > 1.96 and cifre["diferenta_relativa"] > 1
    assert verdict(SLAB, BUN, minim=10, prag=0.2, expirat=False)[0] == "castiga_b"
    aproape = [x + 0.002 for x in SLAB]
    assert verdict(aproape, SLAB, minim=10, prag=0.2, expirat=False)[0] == "fara_diferenta", (
        "sub pragul declarat"
    )
    zgomot_a = [0.01, 0.20, 0.02, 0.15, 0.01, 0.18, 0.02, 0.01, 0.16, 0.02]
    zgomot_b = [0.05, 0.06, 0.05, 0.06, 0.05, 0.06, 0.05, 0.06, 0.05, 0.06]
    c, cifre = verdict(zgomot_a, zgomot_b, minim=10, prag=0.2, expirat=False)
    assert c == "fara_diferenta" and abs(cifre["z"]) < 1.96, "diferență mare în medie, dar nesemnificativă"


def test_cazurile_de_margine_nu_dau_erori() -> None:
    assert verdict([0.05] * 5, [0.05] * 5, minim=5, prag=0.1, expirat=False)[0] == "fara_diferenta"
    c, cifre = verdict([0.05] * 5, [0.0] * 5, minim=5, prag=0.1, expirat=False)
    assert c == "castiga_a" and cifre["z"] is None and cifre["diferenta_relativa"] is None
    assert set(ETICHETE_CONCLUZIE) == {"castiga_a", "castiga_b", "fara_diferenta", "neconcludent"}
