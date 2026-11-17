"""F11.5 — Constituția: garda statică a modulului de învățare și indicatorii de gardă (nuclee pure)."""

import importlib.util
from pathlib import Path

from app.invatare import constitutie

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_invatare", ROOT / "scripts" / "check_invatare.py")
assert spec and spec.loader
garda = importlib.util.module_from_spec(spec)
spec.loader.exec_module(garda)


def test_repo_ul_real_trece_garda() -> None:
    assert garda.verifica(ROOT) == []


def test_garda_prinde_importurile_si_scrierile_interzise() -> None:
    assert garda.probleme("from app.validare import reguli_client\n")[0][1].startswith("import interzis")
    assert garda.probleme("import app.validare.registru\n")
    assert garda.probleme("from app.creier.versiuni import scrie\n")
    assert garda.probleme("p = 'rulepacks/general.toml'\n")
    assert garda.probleme("open('x.toml', 'w').write('a')\n")
    assert garda.probleme("from pathlib import Path\nPath('x').write_text('a')\n")
    assert garda.probleme("from app import validare\nv = validare.VerdictSalvat\nopen('x').read()\n") == [], (
        "citirea verdictelor și a fișierelor rămâne permisă"
    )


def test_indicatorii_de_garda() -> None:
    inainte = {"ascunderi": 0.010, "dezabonari": 0.002, "reclamatii": 0.0}
    assert (
        constitutie.garda_incalcata(inainte, {"ascunderi": 0.011, "dezabonari": 0.002, "reclamatii": 0.0})
        == []
    )
    assert constitutie.garda_incalcata(inainte, {"ascunderi": 0.013, "dezabonari": 0.002}) == ["ascunderi"]
    assert constitutie.garda_incalcata(inainte, {"reclamatii": 0.001}) == ["reclamatii"], "apare de la zero"
    assert constitutie.garda_incalcata({}, {"ascunderi": 0.5}) == [], "fără valoare dinainte nu se judecă"
    assert constitutie.garda_incalcata(inainte, {"aprecieri": 9.0}) == [], (
        "doar indicatorii de gardă contează"
    )
