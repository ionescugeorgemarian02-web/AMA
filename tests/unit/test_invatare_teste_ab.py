"""F14.4 — regula testului formal: mărimea eșantionului, eșantionul fix, verdictul."""

import app.main  # noqa: F401  (ordinea importurilor: ciclul analiza → site → panou → invatare)
from app.invatare.teste_ab import marime_esantion, verdict


def test_marimea_esantionului() -> None:
    assert marime_esantion(0.5, 1.0) == 63  # efect de 0,5 σ, α = 0,05, putere 0,8
    assert marime_esantion(1.0, 1.0) == 20  # minimul
    assert marime_esantion(0.25, 1.0, putere=0.9) > marime_esantion(0.25, 1.0)


def test_verdictul_doar_la_esantionul_declarat() -> None:
    a, b = [0.1, 0.2] * 10, [0.5, 0.6] * 10
    assert verdict(a[:5], b[:5], n=20, alfa=0.05, efect_minim=0.1, expirat=False)[0] is None
    assert verdict(a[:5], b[:5], n=20, alfa=0.05, efect_minim=0.1, expirat=True)[0] == "neconcludent"
    v, c = verdict(a, b, n=20, alfa=0.05, efect_minim=0.1, expirat=False)
    assert v == "castiga_b" and c["diferenta"] == 0.4 and c["p"] < 0.001
    assert verdict(b, a, n=20, alfa=0.05, efect_minim=0.1, expirat=False)[0] == "castiga_a"
    assert (
        verdict(a, list(reversed(a)), n=20, alfa=0.05, efect_minim=0.1, expirat=False)[0] == "fara_diferenta"
    )
    assert (
        verdict([0.3] * 20, [0.3] * 20, n=20, alfa=0.05, efect_minim=0.1, expirat=False)[0]
        == "fara_diferenta"
    )
