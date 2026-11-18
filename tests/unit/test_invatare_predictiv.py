"""F14.3 / F14.5 — nucleul predictiv: AUC, boosting-ul, comparația cu marja, etichetarea pe mediană."""

import datetime as dt
import random
from types import SimpleNamespace

import app.main  # noqa: F401  (ordinea importurilor: ciclul analiza → site → panou → invatare)
from app.invatare import predictiv, predictor

T0 = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)


def test_auc() -> None:
    assert predictiv.auc([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1]) == 0.75
    assert predictiv.auc([0.5, 0.5], [0, 1]) == 0.5
    assert predictiv.auc([0.2, 0.3], [1, 1]) == 0.5


def test_boostingul_invata_un_prag_si_se_serializeaza() -> None:
    rng = random.Random(1)  # noqa: S311
    xs = [[rng.random(), rng.random()] for _ in range(400)]
    y = [int(x[0] > 0.6) for x in xs]
    m = predictiv.antreneaza(["a", "b"], xs, y, runde=20)
    assert predictiv.auc([m.scor(x) for x in xs], y) > 0.95
    assert {c.trasatura for c in m.cioturi} == {0} or m.cioturi[0].trasatura == 0
    m2 = predictiv.Model.din_dict(m.ca_dict())
    assert m2.scor([0.9, 0.1]) == m.scor([0.9, 0.1]) > m.scor([0.1, 0.1])


def test_evaluarea_in_timp_cu_referinta_intamplare_si_reguli() -> None:
    rng = random.Random(2)  # noqa: S311
    ex = []
    for k in range(600):
        tipar = rng.choice(["a", "b", "c"])
        p = 0.75 if tipar == "a" else 0.25
        ex.append(predictiv.Exemplu({"tipar": tipar, "x": rng.random()}, int(rng.random() < p),
                                    T0 + dt.timedelta(days=k), scor_regula=rng.random()))  # fmt: skip
    _, m = predictiv.evalueaza(ex, referinta="intamplare")
    assert m["bate"] and m["n_test"] == 180 and m["interval"][0] > predictiv.MARJA
    _, m = predictiv.evalueaza(ex, referinta="reguli")
    assert m["bate"]  # regula „la noroc” e bătută
    bune = [predictiv.Exemplu(e.trasaturi, e.eticheta, e.moment, scor_regula=float(e.trasaturi["tipar"] == "a"))
            for e in ex]  # fmt: skip
    _, m = predictiv.evalueaza(bune, referinta="reguli")
    assert not m["bate"]  # regula care știe deja tiparul nu e bătută cu marjă


def test_codificarea_si_eticheta_pe_mediana_antrenarii() -> None:
    nume, X = predictiv.codifica([{"t": "a", "o": 3}, {"t": "b", "o": 4}])
    assert nume == ["o", "t=a", "t=b"] and X == [[3.0, 1.0, 0.0], [4.0, 0.0, 1.0]]
    rows = [SimpleNamespace(tipar_hook="h", format="postare", pilon="", unghi="", zi_saptamana=1, ora=9,
                            recompensa=float(i), publicat_la=T0 + dt.timedelta(days=i)) for i in range(10)]  # fmt: skip
    ex = predictor.exemple(rows)
    assert [e.eticheta for e in ex] == [0, 0, 0, 0, 1, 1, 1, 1, 1, 1]  # mediana primelor 7 = 3
