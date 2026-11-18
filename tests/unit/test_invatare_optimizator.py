"""F14.1 — nucleul optimizatorului: setul de aur, împărțirea, scorul compus, regula de câștig."""

import app.main  # noqa: F401  (ordinea importurilor: ciclul analiza → site → panou → invatare)
from app.gateway.prompturi import Reperat
from app.ids import new_id
from app.invatare import optimizator as o


def test_setul_de_aur_al_hookurilor_se_imparte_determinist() -> None:
    ex = o.incarca_set("continut.hookuri")
    assert len(ex) == 20 and len({e.id for e in ex}) == 20
    antr, test = o.imparte(ex)
    assert o.imparte(list(reversed(ex)))[1] == list(reversed(test))  # aceleași exemple, oricum ar fi ordonate
    assert len(test) >= 2 and len(antr) >= 10 and not {e.id for e in antr} & {e.id for e in test}
    assert "continut.hookuri" in o.componente_cu_set()


def test_textul_iesirii_si_evaluarea() -> None:
    ex = o.Exemplu("x", {}, {"cuvinte_obligatorii": ["espresso"], "cuvinte_interzise": ["garantat"]})
    iesire = {"hookuri": [{"text": "Un espresso de dimineață, pregătit aici.", "tipar": "rezultat"}]}
    assert "espresso" in o.text_iesire(iesire)
    assert o.evalueaza_iesire(ex, iesire)[:2] == (1.0, True)
    assert o.evalueaza_iesire(ex, None) == (0.0, False, {"schema_valida": 0.0})
    assert not o.conform("Afla ce pregatim saptamana aceasta in cartier si dupa.")


def test_regula_de_castig_cere_marja_si_conformitate() -> None:
    camp = o.Scor(0.80, 1.0, 6)
    assert o.bate(camp, o.Scor(0.90, 1.0, 6))[0]
    assert not o.bate(camp, o.Scor(0.82, 1.0, 6))[0]  # sub marjă
    ok, motiv = o.bate(camp, o.Scor(1.0, 0.9, 6))
    assert not ok and "conformitate" in motiv
    assert o.Scor(0.5, 0.5, 2).compus == 0.25


def test_reflectia_doar_adauga_instructiuni() -> None:
    camp = Reperat(new_id(), "p", 1, "activ", "creatie", "Regula de bază.", "{{x}}", "app.x.Y")
    p = o.PropunereReflectie(
        incredere=0.7, instructiuni=[{"instructiune": "Folosește cuvinte concrete.", "motiv": "lipseau"}]
    )
    (v,) = o.din_reflectie(camp, p)
    assert v.sistem.startswith("Regula de bază.") and v.sistem.endswith("Folosește cuvinte concrete.")
    assert v.sablon == "{{x}}"
