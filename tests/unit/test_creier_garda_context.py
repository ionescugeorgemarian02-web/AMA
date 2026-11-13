"""F4.6 / F4.7 — garda „niciun fapt neaprobat nu intră în context”: faptele și ofertele ajung la constructorul de context
DOAR prin `fapte.pentru_context` / `oferte.pentru_context` (aprobate de un om și valabile la data cerută). Garda e statică:
verifică ce importă și ce folosește codul care construiește contextul."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CREIER = ROOT / "app" / "creier"
INTERZISE = {"VersiuneCreier", "IntrareCreier", "versiuni", "modele", "Pasaj"}
FUNCTII_CITIRE_INTERZISE = {
    "istoric",
    "citeste",
    "lista",
    "la_data",
    "versiune_aprobata",
    "propuneri",
    "fapt",
}


def _importuri(fisier: Path) -> set[str]:
    nume: set[str] = set()
    for nod in ast.walk(ast.parse(fisier.read_text(encoding="utf-8"))):
        if isinstance(nod, ast.ImportFrom):
            nume.update(a.name for a in nod.names)
            if nod.module:
                nume.add(nod.module.rsplit(".", 1)[-1])
        elif isinstance(nod, ast.Import):
            nume.update(a.name.rsplit(".", 1)[-1] for a in nod.names)
    return nume


def test_constructorul_de_context_nu_citeste_faptele_altfel_decat_prin_pentru_context() -> None:
    module_context = sorted(CREIER.glob("context*.py"))
    for (
        fisier
    ) in module_context:  # F4.7 adaugă `context.py`; până atunci garda nu are ce verifica, dar rămâne activă
        sursa = fisier.read_text(encoding="utf-8")
        assert not (_importuri(fisier) & INTERZISE), f"{fisier.name}: citește direct depozitul versionat"
        arbore = ast.parse(sursa)
        apeluri = {
            n.func.attr
            for n in ast.walk(arbore)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        assert not (apeluri & FUNCTII_CITIRE_INTERZISE), (
            f"{fisier.name}: {apeluri & FUNCTII_CITIRE_INTERZISE}"
        )
        assert "pentru_context" in sursa, f"{fisier.name}: faptele trebuie citite prin pentru_context"


def test_in_afara_creierului_nimeni_nu_atinge_tabelele_versionate() -> None:
    gasite = []
    for fisier in (ROOT / "app").rglob("*.py"):
        rel = fisier.relative_to(ROOT).as_posix()
        if rel.startswith("app/creier/"):
            continue
        for nod in ast.walk(ast.parse(fisier.read_text(encoding="utf-8"))):
            nume = [a.name for a in nod.names] if isinstance(nod, ast.Import) else []
            if isinstance(nod, ast.ImportFrom) and nod.module:
                nume = [nod.module, *[f"{nod.module}.{a.name}" for a in nod.names]]
            gasite += [(rel, n) for n in nume if n in ("app.creier.modele", "app.creier.versiuni")]
    assert gasite == [], gasite


def test_fapte_si_oferte_au_o_singura_functie_publica_de_citire_pentru_context() -> None:
    from app.creier import fapte, oferte

    for modul in (fapte, oferte):
        publice = [n for n in dir(modul) if n.startswith("pentru_context")]
        assert publice == ["pentru_context"]
