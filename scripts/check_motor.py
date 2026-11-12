#!/usr/bin/env python3
"""Garda motorului (F2.1, ADR-03): biblioteca de workflow-uri (`dbos`) se importă într-un singur loc.

Restul aplicației folosește `app.operare.motor`. Pică dacă un fișier Python din repo, în afara
`app/operare/motor/`, importă `dbos` (direct, cu `from`, prin `importlib.import_module` sau `__import__`).
Folosire: check_motor.py [rădăcina repo-ului]
"""

import ast
import subprocess
import sys
from pathlib import Path

PERMIS = "app/operare/motor/"
BIBLIOTECA = "dbos"


def _este_dbos(nume: str | None) -> bool:
    return bool(nume) and (nume == BIBLIOTECA or str(nume).startswith(BIBLIOTECA + "."))


def importuri_dbos(sursa: str) -> list[int]:
    """Liniile care importă `dbos` în această sursă."""
    linii: list[int] = []
    for nod in ast.walk(ast.parse(sursa)):
        if (
            (isinstance(nod, ast.Import) and any(_este_dbos(a.name) for a in nod.names))
            or (isinstance(nod, ast.ImportFrom) and nod.level == 0 and _este_dbos(nod.module))
            or (
                isinstance(nod, ast.Call)
                and isinstance(nod.func, ast.Name | ast.Attribute)
                and getattr(nod.func, "id", getattr(nod.func, "attr", "")) in ("import_module", "__import__")
                and nod.args
                and isinstance(nod.args[0], ast.Constant)
                and _este_dbos(str(nod.args[0].value))
            )
        ):
            linii.append(nod.lineno)
    return linii


def fisiere_python(root: Path) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return [f for f in out.splitlines() if f]
    except (OSError, subprocess.CalledProcessError):
        return [str(p.relative_to(root)) for p in root.rglob("*.py") if ".venv" not in p.parts]


def verifica(root: Path) -> list[str]:
    erori: list[str] = []
    for rel in fisiere_python(root):
        if rel.startswith(PERMIS) or rel.startswith("tests/fixtures/"):
            continue
        fisier = root / rel
        if not fisier.is_file():
            continue
        for linie in importuri_dbos(fisier.read_text(encoding="utf-8")):
            erori.append(f"{rel}:{linie}: `dbos` se importă doar în {PERMIS} (folosește app.operare.motor)")
    return erori


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1]
    erori = verifica(root)
    for e in erori:
        print(e, file=sys.stderr)
    if erori:
        return 1
    print("garda motorului: biblioteca de workflow-uri este importată doar în app/operare/motor/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
