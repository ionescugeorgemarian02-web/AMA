#!/usr/bin/env python3
"""Garda de dependențe (F1.2): pică dacă o dependență nu este fixată exact sau dacă lipsește un hash.

Verifică:
  1. fiecare dependență din pyproject.toml are forma `nume==versiune`;
  2. fiecare pachet din uv.lock are hash-uri (sau este proiectul însuși);
  3. imaginile din Dockerfile și din fișierele compose sunt fixate pe amprentă (@sha256:…);
  4. acțiunile GitHub sunt fixate pe SHA de commit, nu pe etichetă.
Folosire: check_pins.py [rădăcina repo-ului]
"""

import re
import sys
import tomllib
from pathlib import Path

PIN = re.compile(r"^[A-Za-z0-9_.\-]+(\[[A-Za-z0-9_,.\-]+\])?==[A-Za-z0-9_.!+\-]+(\s*;.*)?$")
IMAGE_LINE = re.compile(r"^\s*(?:FROM\s+(?:--platform=\S+\s+)?|image:\s*)[\"']?([^\s\"']+)", re.IGNORECASE)
USES_LINE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
SHA = re.compile(r"@[0-9a-f]{40}$")


def check_pyproject(root: Path) -> list[str]:
    errors: list[str] = []
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    groups: dict[str, list[object]] = {"dependencies": data.get("project", {}).get("dependencies", [])}
    for name, deps in data.get("project", {}).get("optional-dependencies", {}).items():
        groups[f"optional:{name}"] = deps
    for name, deps in data.get("dependency-groups", {}).items():
        groups[f"group:{name}"] = deps
    for group, deps in groups.items():
        for dep in deps:
            if not isinstance(dep, str) or not PIN.match(dep.strip()):
                errors.append(f"pyproject.toml [{group}]: dependență nefixată exact: {dep!r}")
    return errors


def check_lock(root: Path) -> list[str]:
    lock = root / "uv.lock"
    if not lock.exists():
        return ["uv.lock lipsește"]
    errors: list[str] = []
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    for pkg in data.get("package", []):
        source = pkg.get("source", {})
        if "virtual" in source or "editable" in source:
            continue
        files = [*pkg.get("wheels", []), *([pkg["sdist"]] if "sdist" in pkg else [])]
        if not files or any(not str(f.get("hash", "")).startswith("sha256:") for f in files):
            errors.append(f"uv.lock: pachet fără hash: {pkg.get('name')}")
    return errors


def check_images(root: Path) -> list[str]:
    errors: list[str] = []
    files = [*root.glob("Dockerfile*"), *root.glob("infra/**/Dockerfile*"), *root.glob("infra/**/*.yml")]
    files += [*root.glob("infra/**/*.yaml"), *root.glob("compose*.y*ml")]
    for path in sorted(set(files)):
        stages: set[str] = set()
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = IMAGE_LINE.match(line)
            if not m:
                continue
            image = m.group(1)
            stage = re.search(r"\s+AS\s+(\S+)", line, re.IGNORECASE)
            if stage:
                stages.add(stage.group(1).lower())
            if image.lower() in stages or image == "scratch" or image.startswith("${"):
                continue
            if "@sha256:" not in image:
                errors.append(f"{path.relative_to(root)}:{n}: imagine nefixată pe amprentă: {image}")
    return errors


def check_actions(root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted((root / ".github").glob("**/*.y*ml")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = USES_LINE.match(line)
            if m and not m.group(1).startswith("./") and not SHA.search(m.group(1)):
                errors.append(f"{path.relative_to(root)}:{n}: acțiune nefixată pe SHA: {m.group(1)}")
    return errors


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors = check_pyproject(root) + check_lock(root) + check_images(root) + check_actions(root)
    for e in errors:
        print(f"EROARE: {e}")
    if errors:
        print(f"\n{len(errors)} probleme. Fixează versiunile (==), amprentele (@sha256:) și SHA-urile.")
        return 1
    print("Dependențe, imagini și acțiuni: toate fixate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
