#!/usr/bin/env python3
"""Garda Constituției (F11.5, docs/11 §11.6, punctul 1): modulul de învățare nu poate atinge validatorii.

În `app/invatare/` sunt interzise:
- importul regulilor, al registrului de validatori, al pachetelor de reguli și al scrierii de fapte
  (`app.validare.reguli`, `.reguli_client`, `.registru`, `.politici`, `.date_validare`, `app.creier.fapte`,
  `app.creier.versiuni`);
- deschiderea de fișiere pentru scriere și orice referire la directorul `rulepacks`.
Citirea verdictelor salvate (`app.validare` ca pachet) rămâne permisă: Reflectorul are nevoie de ele.
Folosire: check_invatare.py [rădăcina repo-ului]
"""

import ast
import sys
from pathlib import Path

INTERZISE = (
    "app.validare.reguli",
    "app.validare.reguli_client",
    "app.validare.registru",
    "app.validare.politici",
    "app.validare.date_validare",
    "app.creier.fapte",
    "app.creier.versiuni",
)
MODURI_SCRIERE = set("wax+")


def probleme(sursa: str) -> list[tuple[int, str]]:
    gasite: list[tuple[int, str]] = []
    for nod in ast.walk(ast.parse(sursa)):
        nume: list[str] = []
        if isinstance(nod, ast.Import):
            nume = [a.name for a in nod.names]
        elif isinstance(nod, ast.ImportFrom) and nod.module:
            nume = [nod.module, *(f"{nod.module}.{a.name}" for a in nod.names)]
        for n in nume:
            if any(n == i or n.startswith(i + ".") for i in INTERZISE):
                gasite.append((nod.lineno, f"import interzis: {n}"))
        if isinstance(nod, ast.Constant) and isinstance(nod.value, str) and "rulepacks" in nod.value:
            gasite.append((nod.lineno, "referire la pachetele de reguli (rulepacks)"))
        if isinstance(nod, ast.Call) and getattr(nod.func, "id", getattr(nod.func, "attr", "")) in (
            "open",
            "write_text",
            "write_bytes",
        ):
            mod = next((k.value for k in nod.keywords if k.arg == "mode"), None) or (
                nod.args[1] if len(nod.args) > 1 else None
            )
            scrie = getattr(nod.func, "attr", "") in ("write_text", "write_bytes") or (
                isinstance(mod, ast.Constant)
                and isinstance(mod.value, str)
                and set(mod.value) & MODURI_SCRIERE
            )
            if scrie:
                gasite.append((nod.lineno, "scriere de fișiere din modulul de învățare"))
    return gasite


def verifica(root: Path) -> list[str]:
    erori = []
    for f in sorted((root / "app" / "invatare").rglob("*.py")):
        for linie, ce in probleme(f.read_text(encoding="utf-8")):
            erori.append(f"{f.relative_to(root)}:{linie}: {ce} (Constituția învățării, docs/11 §11.6)")
    return erori


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1]
    erori = verifica(root)
    for e in erori:
        print(e, file=sys.stderr)
    if erori:
        return 1
    print("garda Constituției: modulul de învățare nu atinge validatorii, regulile sau faptele")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
