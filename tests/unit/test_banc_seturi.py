"""F5.7 — seturile de aur: formatul, mărimile cerute (30–100 pe validator, ≥ 100 greșite, ≥ 60 bune),
înghețarea (amprentele
puse de un om) și garda: niciun cod din `app/` nu scrie în `evaluare/`."""

import json
import re
from pathlib import Path

import pytest

from app.validare.banc import seturi
from app.validare.banc.seturi import SetInvalid

ROOT = Path(__file__).resolve().parents[2]
SCRIERE = re.compile(
    r"\b(write_text|write_bytes|unlink|rmtree|rename|replace_file|truncate|mkdir|touch|symlink_to|hardlink_to|chmod|"
    r"copyfile|copytree|move)\s*\(|open\([^)]*[\"'](?:[wax+]|[rb]\+)b?[\"']|\bshutil\b|\bos\.(remove|rename|unlink|replace)\b"
)


@pytest.fixture(scope="module")
def s() -> seturi.Seturi:
    return seturi.incarca()


def test_marimile_cerute(s: seturi.Seturi) -> None:
    assert set(s.aur) == set(seturi.VALIDATORI)
    for g, exemple in s.aur.items():
        assert 30 <= len(exemple) <= 100, (g, len(exemple))
        # fiecare set are și cazuri care trebuie să treacă, și cazuri care trebuie prinse
        assert {e.asteptat for e in exemple} == {"trece", "esec"}, g
    assert len(s.rele) >= 100 and len(s.bune) >= 60
    assert {e.validator for e in s.rele} == set(seturi.VALIDATORI), (
        "fiecare validator are materiale greșite vizate"
    )


def test_identificatori_unici_si_contexte_existente(s: seturi.Seturi) -> None:
    toate = [e for v in s.aur.values() for e in v] + list(s.rele) + list(s.bune)
    ids = [e.id for e in toate]
    assert len(ids) == len(set(ids))
    assert {e.ctx for e in toate} <= set(s.contexte)
    assert s.la.tzinfo is not None


def test_seturile_sunt_inghetate_amprentele_puse_de_om_se_potrivesc() -> None:
    """O schimbare a seturilor cere un commit care actualizează și `INGHETAT.toml` (gest uman, cu motiv)."""
    assert seturi.inghetat() == seturi.amprente_baza(), (
        "seturile de aur s-au schimbat fără actualizarea înghețării"
    )
    assert set(seturi.inghetat()) == set(seturi.FISIERE_BAZA)


def test_fara_date_personale_reale() -> None:
    telefon = re.compile(r"(?<!\d)(?:\+?40|0)7\d{2}[ .-]?\d{3}[ .-]?\d{3}(?!\d)")
    cnp = re.compile(r"(?<!\d)[1-8]\d{12}(?!\d)")
    email = re.compile(r"(?<![:/\w])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
    for f in seturi.FISIERE_BAZA:
        t = (seturi.DIRECTOR / f).read_text(encoding="utf-8")
        assert not telefon.search(t), f
        assert not cnp.search(t), f
        gasite = [
            m.group()
            for m in email.finditer(t)
            if not re.search(
                r"https?://[^@\s]*$", t[: m.start()].split()[-1] if t[: m.start()].split() else ""
            )
        ]
        assert all(g.endswith((".test", ".example")) for g in gasite), (f, gasite)


def test_formatul_e_verificat(tmp_path: Path) -> None:
    for f in seturi.FISIERE_BAZA:
        (tmp_path / f).write_bytes((seturi.DIRECTOR / f).read_bytes())
    bun = seturi.incarca(tmp_path)
    assert bun.amprenta == seturi.amprenta_seturi()
    rand = {
        "id": "x-1",
        "ctx": "gol",
        "tip": "postare",
        "canal": "facebook",
        "text": "Text.",
        "asteptat": "esec",
        "motiv": "m",
    }
    (tmp_path / "G1.jsonl").write_text(json.dumps(rand) + "\n", encoding="utf-8")
    with pytest.raises(SetInvalid, match="severitate"):
        seturi.incarca(tmp_path)
    (tmp_path / "G1.jsonl").write_text(
        json.dumps({**rand, "severitate": "majora", "ctx": "inexistent"}) + "\n", encoding="utf-8"
    )
    with pytest.raises(SetInvalid, match="contextul"):
        seturi.incarca(tmp_path)
    (tmp_path / "G1.jsonl").write_text("{nu e json\n", encoding="utf-8")
    with pytest.raises(SetInvalid, match="JSON invalid"):
        seturi.incarca(tmp_path)


def test_garda_niciun_cod_nu_scrie_in_seturi() -> None:
    surse = {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8") for p in (ROOT / "app").rglob("*.py")}
    numesc = {
        p for p, t in surse.items() if re.search(r"[\"']evaluare[\"']\s*/\s*[\"']aur[\"']|evaluare/aur", t)
    }
    assert numesc <= {
        "app/validare/banc/seturi.py",
        "app/validare/banc/__init__.py",
        "app/validare/exemple.py",
    }, numesc
    cod = "\n".join(
        linie
        for linie in surse["app/validare/banc/seturi.py"].splitlines()
        if not linie.strip().startswith("#")
    )
    assert not SCRIERE.search(cod), "încărcătorul seturilor scrie fișiere"
    assert "read_bytes()" in cod
    for cale, t in surse.items():
        if cale != "app/validare/banc/seturi.py":
            assert not re.search(
                r"seturi\.DIRECTOR|from app\.validare\.banc\.seturi import[^\n]*\bDIRECTOR\b", t
            ), cale
    exemple = "\n".join(
        linie for linie in surse["app/validare/exemple.py"].splitlines() if not linie.strip().startswith("#")
    )
    assert not SCRIERE.search(exemple), "exemplele promovate nu se scriu în depozit din cod"
