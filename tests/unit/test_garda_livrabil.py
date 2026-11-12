"""F2.3 — garda: starea unui livrabil se schimbă doar în `app/productie/tranzitii.py` (peste declanșatorul din bază)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
PERMIS = "app/productie/tranzitii.py"

# Scrieri de stare pe un livrabil: atribut, UPDATE brut sau `update(Livrabil)`.
SABLOANE = [
    re.compile(r"\blivrabil\w*\.stare\s*=(?!=)"),
    re.compile(r"\bl\.stare\s*=(?!=)"),
    re.compile(r"UPDATE\s+livrabile\b", re.IGNORECASE),
    re.compile(r"\bupdate\(\s*Livrabil\b"),
    re.compile(r"\binsert\(\s*Livrabil\b"),
]


def test_starea_livrabilului_se_scrie_doar_in_tranzitii() -> None:
    gasite = []
    for p in APP.rglob("*.py"):
        rel = str(p.relative_to(ROOT))
        if rel == PERMIS:
            continue
        text = p.read_text(encoding="utf-8")
        for sablon in SABLOANE:
            if sablon.search(text):
                gasite.append((rel, sablon.pattern))
    assert not gasite, f"starea unui livrabil se scrie doar în {PERMIS}: {gasite}"


def test_garda_prinde_o_scriere_directa() -> None:
    """Garda nu e oarbă: recunoaște exact felurile de scriere pe care le interzice."""
    for exemplu in (
        "livrabil.stare = 'gata'",
        "UPDATE livrabile SET stare = 'x'",
        "update(Livrabil).values(stare=1)",
    ):
        assert any(s.search(exemplu) for s in SABLOANE), exemplu
    assert not any(s.search("if livrabil.stare == 'gata':") for s in SABLOANE)
