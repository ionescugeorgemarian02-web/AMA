#!/usr/bin/env python3
"""Garda efectelor externe (F2.5, AGENTS.md): conectorii de efecte se cheamă doar din executor.

Registrul conectorilor (`app.connectors.registru`) și orice pachet de conector (de ex. `.facebook`) se
importă doar în `app/operare/efecte/` (executorul), în `app/connectors/` (conectorii înșiși) și în `tests/`.
Rămân importabile de oriunde: contractul (`app.connectors.contract`: doar tipuri) și botul Telegram
(`app.connectors.telegram`, un canal de notificare, nu un efect asupra clienților). Încărcarea modulelor de
conectori de către worker se face prin nume de modul (text), nu prin import.
Folosire: check_efecte.py [rădăcina repo-ului]
"""

import ast
import subprocess
import sys
from pathlib import Path

PACHET = "app.connectors"
LIBERE = {"contract", "telegram"}  # submodule importabile de oriunde
PERMISE = ("app/operare/efecte/", "app/connectors/", "tests/")


def _submodul(nume: str) -> str | None:
    """`app.connectors.facebook.api` → `facebook`; `app.connectors` → None."""
    if nume == PACHET:
        return None
    if nume.startswith(PACHET + "."):
        return nume[len(PACHET) + 1 :].split(".")[0]
    return ""  # alt pachet


def importuri_interzise(sursa: str) -> list[tuple[int, str]]:
    gasite: list[tuple[int, str]] = []
    for nod in ast.walk(ast.parse(sursa)):
        nume: list[str] = []
        if isinstance(nod, ast.Import):
            nume = [a.name for a in nod.names]
        elif isinstance(nod, ast.ImportFrom) and nod.level == 0 and nod.module:
            nume = [f"{PACHET}.{a.name}" for a in nod.names] if nod.module == PACHET else [nod.module]
        elif (
            isinstance(nod, ast.Call)
            and getattr(nod.func, "id", getattr(nod.func, "attr", "")) in ("import_module", "__import__")
            and nod.args
            and isinstance(nod.args[0], ast.Constant)
            and isinstance(nod.args[0].value, str)
        ):
            nume = [nod.args[0].value]
        for n in nume:
            sub = _submodul(n)
            if sub and sub not in LIBERE:
                gasite.append((nod.lineno, n))
    return gasite


def fisiere_python(root: Path) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout  # fmt: skip
        return [f for f in out.splitlines() if f]
    except (OSError, subprocess.CalledProcessError):
        return [str(p.relative_to(root)) for p in root.rglob("*.py") if ".venv" not in p.parts]


def verifica(root: Path) -> list[str]:
    erori: list[str] = []
    for rel in fisiere_python(root):
        if rel.startswith(PERMISE):
            continue
        fisier = root / rel
        if not fisier.is_file():
            continue
        for linie, nume in importuri_interzise(fisier.read_text(encoding="utf-8")):
            erori.append(
                f"{rel}:{linie}: `{nume}` se importă doar din executorul de efecte "
                "(app/operare/efecte/): efectele externe se cer cu `efecte.cere`"
            )
    return erori


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1]
    erori = verifica(root)
    for e in erori:
        print(e, file=sys.stderr)
    if erori:
        return 1
    print("garda efectelor: conectorii se cheamă doar din executorul de efecte (app/operare/efecte/)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
