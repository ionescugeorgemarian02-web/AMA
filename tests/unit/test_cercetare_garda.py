"""F4.2 — descărcarea de pagini este CITIRE, nu efect extern: colectorul trăiește în `app/cercetare`, nu importă
conectorii și nu trece prin executorul de efecte; garda efectelor (`scripts/check_efecte.py`) rămâne neschimbată."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_colectorul_nu_importa_conectori_nici_executorul_de_efecte() -> None:
    gasite = []
    for fisier in (ROOT / "app" / "cercetare").glob("*.py"):
        for nod in ast.walk(ast.parse(fisier.read_text(encoding="utf-8"))):
            nume = [a.name for a in nod.names] if isinstance(nod, ast.Import) else []
            if isinstance(nod, ast.ImportFrom) and nod.module:
                nume = [nod.module]
            gasite += [
                (fisier.name, n) for n in nume if n.startswith(("app.connectors", "app.operare.efecte"))
            ]
    assert gasite == []


def test_garda_efectelor_trece_pe_arborele_curent_fara_exceptii_pentru_cercetare() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import check_efecte  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)
    assert check_efecte.verifica(ROOT) == []
    assert "cercetare" not in check_efecte.PERMISE and not any("cercetare" in p for p in check_efecte.PERMISE)
