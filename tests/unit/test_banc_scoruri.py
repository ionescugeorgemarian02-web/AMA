"""F5.7 — nucleul pur al bancului de evaluare: matricea de confuzie, precizia / recall-ul, ratele și poarta
F5."""

import pytest

from app.validare.banc import scoruri
from app.validare.banc.executie import RezultatExemplu, calculeaza
from app.validare.banc.seturi import Exemplu, Seturi


def test_confuzia_numara_corect_si_ratele_sunt_cele_definite() -> None:
    perechi = [(True, True)] * 8 + [(True, False)] * 2 + [(False, True)] * 1 + [(False, False)] * 9
    c = scoruri.confuzie(perechi)
    assert (c.tp, c.fn, c.fp, c.tn, c.total) == (8, 2, 1, 9, 20)
    assert c.precizie == pytest.approx(8 / 9, abs=1e-4)
    assert c.recall == 0.8
    assert c.rata_fals_pozitive == 0.1
    assert c.acuratete == 0.85


def test_fara_numitor_nu_se_pretinde_o_rata() -> None:
    c = scoruri.confuzie([(False, False)])
    assert c.precizie is None and c.recall is None and c.rata_fals_pozitive == 0.0
    assert scoruri.rata(0, 0) is None


def test_matricea_pe_clase_si_acordul_de_severitate() -> None:
    perechi = [
        ("critica", "critica"),
        ("critica", "majora"),
        ("majora", "majora"),
        ("trece", "majora"),
        ("trece", "trece"),
    ]
    m = scoruri.matrice(perechi)
    assert m["critica"] == {"trece": 0, "majora": 1, "critica": 1}
    assert m["trece"]["majora"] == 1 and m["trece"]["trece"] == 1
    assert sum(sum(r.values()) for r in m.values()) == len(perechi)
    assert scoruri.acord_severitate(perechi) == pytest.approx(2 / 3, abs=1e-4)
    assert scoruri.clasa(False, "critica") == "trece" and scoruri.clasa(True, None) == "majora"


@pytest.mark.parametrize(
    ("rele", "blocate", "bune", "respinse", "trece"),
    [
        (100, 95, 60, 6, True),  # exact la praguri
        (100, 94, 60, 0, False),  # sub 95%
        (100, 100, 60, 7, False),  # peste 10%
        (0, 0, 60, 0, False),  # set gol: nu dovedește nimic
        (100, 100, 0, 0, False),
    ],
)
def test_poarta_f5(rele: int, blocate: int, bune: int, respinse: int, trece: bool) -> None:
    p = scoruri.poarta(rele, blocate, bune, respinse)
    assert p.trece is trece
    assert p.json()["prag_blocare"] == 0.95 and p.json()["prag_respingere_pe_nedrept"] == 0.10


def _e(id_: str, set_: str, validator: str, **kw: object) -> Exemplu:
    return Exemplu(
        id=id_, set=set_, ctx="gol", tip="postare", canal="facebook", text="x", validator=validator, **kw
    )  # type: ignore[arg-type]


def test_calculul_pe_validator_si_pe_seturi() -> None:
    import datetime as dt

    rele = (_e("r1", "rele", "G2", defect="preț"), _e("r2", "rele", "G2", defect="preț"))
    bune = (_e("b1", "bune", "", motiv="ok"), _e("b2", "bune", "", motiv="ok"))
    s = Seturi(
        la=dt.datetime(2026, 11, 12, tzinfo=dt.UTC),
        contexte={},
        aur={},
        rele=rele,
        bune=bune,
        amprenta="a" * 64,
    )
    rez = [
        RezultatExemplu("g1", "aur:G2", "G2", "majora", "majora", ["G2"]),
        RezultatExemplu("g2", "aur:G2", "G2", "trece", "majora", ["G2"]),
        RezultatExemplu("g3", "promovat:G2", "G2", "critica", "trece"),
        RezultatExemplu("r1", "rele", "G2", "blocat", "blocat", ["G2"]),
        RezultatExemplu("r2", "rele", "G2", "blocat", "trece"),
        RezultatExemplu("b1", "bune", "", "trece", "trece"),
        RezultatExemplu("b2", "bune", "", "trece", "blocat", ["G3"]),
    ]
    sc = calculeaza(s, rez)
    g2 = sc["validatori"]["G2"]
    assert (g2["tp"], g2["fp"], g2["fn"], g2["tn"], g2["exemple"], g2["promovate"]) == (1, 1, 1, 0, 3, 1)
    assert [x["id"] for x in g2["gresite"]] == ["g2", "g3"]
    assert sc["rele"]["blocate"] == 1 and sc["rele"]["pe_validator"]["G2"]["scapate"] == [
        {"id": "r2", "defect": "preț"}
    ]
    assert sc["bune"]["respinse_de"] == {"G3": 1}
    assert sc["poarta"]["rata_blocare"] == 0.5 and sc["poarta"]["trece"] is False
