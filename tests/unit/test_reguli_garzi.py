"""F5.4 — garda: regulile se schimbă doar prin revizuire umană. Niciun modul din `app/` nu scrie în `rulepacks/`, iar singurul care
le citește (`app/validare/reguli.py`) nu are nicio cale de scriere."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
PRIMIT = "app/validare/reguli.py"
SCRIERE = re.compile(
    r"\b(write_text|write_bytes|unlink|rmtree|rename|replace_file|truncate|mkdir|touch|symlink_to|hardlink_to|chmod|"
    r"copyfile|copytree|move)\s*\(|open\([^)]*[\"'](?:[wax+]|[rb]\+)b?[\"']|\bshutil\b|\bos\.(remove|rename|unlink|replace)\b"
)


def surse() -> dict[str, str]:
    return {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8") for p in APP.rglob("*.py")}


def test_numai_incarcatorul_cunoaste_directorul_de_reguli() -> None:
    gasite = {p for p, s in surse().items() if re.search(r"rulepacks|DIRECTOR_REGULI", s)}
    # `reguli.py` îl definește; modulele care îl folosesc doar prin `reguli.incarca` nu îl numesc
    assert gasite <= {PRIMIT, "app/validare/__init__.py"}, (
        f"module care ating rulepacks/: {sorted(gasite - {PRIMIT})}"
    )


def test_incarcatorul_nu_are_nicio_cale_de_scriere() -> None:
    s = surse()[PRIMIT]
    cod = "\n".join(linie for linie in s.splitlines() if not linie.strip().startswith("#"))
    assert not SCRIERE.search(cod), f"reguli.py scrie fișiere: {SCRIERE.search(cod)}"
    assert "read_bytes()" in cod, "fișierele se citesc doar ca octeți"


def test_nicio_cale_din_app_nu_construieste_o_scriere_spre_pachete() -> None:
    """Nici un modul nu importă `DIRECTOR` din reguli ca să scrie: se caută importul simbolului în afara încărcătorului."""
    for cale, s in surse().items():
        if cale == PRIMIT:
            continue
        assert not re.search(r"from app\.validare\.reguli import[^\n]*\bDIRECTOR\b", s), cale
        assert not re.search(r"reguli\.DIRECTOR", s), cale


def test_garda_prinde_o_scriere_daca_ar_exista() -> None:
    assert SCRIERE.search('Path("x").write_text("a")')
    assert SCRIERE.search('open(cale, "w")')
    assert not SCRIERE.search("cale.read_bytes()")
