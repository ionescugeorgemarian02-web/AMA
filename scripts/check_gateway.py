#!/usr/bin/env python3
"""Garda gateway-ului (F3.2, ADR-04, AGENTS.md: „Apeluri la modele în afara `app/gateway`”).

Pică dacă un fișier Python din repo:
1. în afara `app/gateway/`, `tests/` și `migrations/` (sămânța): importă un submodul al gateway-ului
   (`app.gateway.client`, `app.gateway.adaptoare`, …; se folosește doar `from app import gateway` /
   `from app.gateway import …`);
2. în afara `app/gateway/`, `tests/` și `migrations/`: conține adresa unui furnizor de modele (nume de
   gazdă ca `api.anthropic.com`, `openrouter.ai`) într-un literal text;
3. oriunde: importă SDK-ul unui furnizor (`openai`, `anthropic`, `groq`, `google.generativeai`, `litellm`, …):
   gateway-ul vorbește cu furnizorii doar prin `httpx`.
Folosire: check_gateway.py [rădăcina repo-ului]
"""

import ast
import subprocess
import sys
from pathlib import Path

PACHET = "app.gateway"
INTERN = "app/gateway/"
PERMISE_IMPORT = ("app/gateway/", "tests/", "migrations/")  # migrările își citesc sămânța (date)
PERMISE_ADRESE = ("app/gateway/", "tests/", "migrations/")
GAZDE = (
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "openrouter.ai",
    "api.groq.com",
    "api.cloudflare.com",
    "api.mistral.ai",
    "api.cohere.com",
    "api.together.xyz",
    "api.deepseek.com",
    "api.x.ai",
    "api.cerebras.ai",
)
SDK = (
    "openai",
    "anthropic",
    "groq",
    "cohere",
    "mistralai",
    "litellm",
    "langchain",
    "google.generativeai",
    "google.genai",
    "together",
    "ollama",
)


def _nume_importate(nod: ast.AST) -> list[str]:
    if isinstance(nod, ast.Import):
        return [a.name for a in nod.names]
    if isinstance(nod, ast.ImportFrom) and nod.level == 0 and nod.module:
        if nod.module == "app":
            return [f"app.{a.name}" for a in nod.names]
        return [nod.module]
    if (
        isinstance(nod, ast.Call)
        and getattr(nod.func, "id", getattr(nod.func, "attr", "")) in ("import_module", "__import__")
        and nod.args
        and isinstance(nod.args[0], ast.Constant)
        and isinstance(nod.args[0].value, str)
    ):
        return [nod.args[0].value]
    return []


def _este_sdk(nume: str) -> bool:
    return any(nume == s or nume.startswith(s + ".") for s in SDK)


def _submodul_gateway(nume: str) -> bool:
    return nume.startswith(PACHET + ".")


def interne(root: Path) -> set[str]:
    """Submodulele gateway-ului care NU sunt exportate de `app/gateway/__init__.py` (în `__all__`)."""
    director = root / "app" / "gateway"
    if not director.is_dir():
        return set()
    module = {p.stem for p in director.glob("*.py") if p.stem != "__init__"}
    module |= {p.name for p in director.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
    exportate: set[str] = set()
    init = director / "__init__.py"
    if init.is_file():
        for nod in ast.walk(ast.parse(init.read_text(encoding="utf-8"))):
            if isinstance(nod, ast.Assign) and any(getattr(t, "id", "") == "__all__" for t in nod.targets):
                exportate = {e.value for e in getattr(nod.value, "elts", []) if isinstance(e, ast.Constant)}
    return module - exportate


def probleme(rel: str, sursa: str, ascunse: set[str]) -> list[str]:
    erori: list[str] = []
    arbore = ast.parse(sursa)
    in_afara = not rel.startswith(PERMISE_IMPORT)
    for nod in ast.walk(arbore):
        if (
            in_afara
            and isinstance(nod, ast.ImportFrom)
            and nod.level == 0
            and nod.module == PACHET
            and any(a.name in ascunse for a in nod.names)
        ) or (
            in_afara
            and isinstance(nod, ast.Attribute)
            and isinstance(nod.value, ast.Name)
            and nod.value.id == "gateway"
            and nod.attr in ascunse
        ):
            erori.append(f"{rel}:{nod.lineno}: submodul intern al gateway-ului: folosește `app.gateway`")
        for nume in _nume_importate(nod):
            linie = getattr(nod, "lineno", 0)
            if _este_sdk(nume):
                erori.append(f"{rel}:{linie}: SDK de furnizor `{nume}`: gateway-ul folosește doar `httpx`")
            elif _submodul_gateway(nume) and in_afara:
                erori.append(f"{rel}:{linie}: `{nume}` este intern gateway-ului: importă din `app.gateway`")
        if (
            isinstance(nod, ast.Constant)
            and isinstance(nod.value, str)
            and not rel.startswith(PERMISE_ADRESE)
            and any(g in nod.value.lower() for g in GAZDE)
        ):
            erori.append(
                f"{rel}:{nod.lineno}: adresă de furnizor de modele în afara `{INTERN}`: apelurile la modele "
                "trec doar prin gateway"
            )
    return erori


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
    ascunse = interne(root)
    for rel in fisiere_python(root):
        fisier = root / rel
        if not fisier.is_file():
            continue
        if rel == "scripts/check_gateway.py":
            continue  # lista de gazde interzise e chiar aici
        erori.extend(probleme(rel, fisier.read_text(encoding="utf-8"), ascunse))
    return erori


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1]
    erori = verifica(root)
    for e in erori:
        print(e, file=sys.stderr)
    if erori:
        return 1
    print("garda gateway-ului: apelurile la modele trec doar prin app/gateway")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
