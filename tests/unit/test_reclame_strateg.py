"""F13.6 — regulile Strategului: patru ieșiri plus „așteaptă”, oprirea după două ferestre slabe."""

from app.reclame.plan import CriteriiOprire
from app.reclame.rezultate import Totaluri
from app.reclame.strateg import judeca

C = CriteriiOprire(cost_tinta_bani=4_000)
SLABA = Totaluri(cheltuiala_bani=45_000, afisari=20_000, clicuri=300, rezultate=2)  # CPR 225 lei > 3 × 40
BUNA = Totaluri(cheltuiala_bani=45_000, afisari=20_000, clicuri=300, rezultate=15)  # CPR 30 lei
MEDIE = Totaluri(cheltuiala_bani=45_000, afisari=20_000, clicuri=300, rezultate=6)  # CPR 75 lei
PUTINE = Totaluri(cheltuiala_bani=3_000, afisari=400, clicuri=5, rezultate=0)


def test_iesirile() -> None:
    assert judeca([PUTINE, SLABA], C).iesire == "asteapta"
    assert judeca([BUNA, SLABA], C).iesire == "continua"
    assert judeca([MEDIE, SLABA], C).iesire == "ajusteaza"
    assert judeca([SLABA, BUNA], C).iesire == "pivoteaza"
    v = judeca([SLABA, SLABA, BUNA], C)
    assert v.iesire == "opreste" and v.motiv.startswith("2 ferestre la rând")
    fara = Totaluri(cheltuiala_bani=9_000, afisari=5_000, clicuri=60, rezultate=0)
    assert judeca([fara, fara], C).iesire == "opreste"
