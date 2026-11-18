"""F15.1: catalogul acoperă exact scenariile din docs/25 §25.3 și fiecare nod trimite la un test care există."""

import ast
import re
from pathlib import Path

from tests.avarie.catalog import SCENARII, noduri

ROOT = Path(__file__).resolve().parents[2]


def _scenarii_din_document() -> list[str]:
    text = (ROOT / "docs" / "25-testare-lansare-pe-vps-si-criterii-de-go-live.md").read_text()
    sectiune = text.split("### 25.3", 1)[1].split("\n### ", 1)[0]
    randuri = [r for r in sectiune.splitlines() if r.startswith("| ") and not r.startswith("| Scenariu")]
    return [re.split(r"\s*\|\s*", r.strip("| "))[0] for r in randuri if not set(r) <= set("|- ")]


def test_catalogul_are_fiecare_scenariu_din_25_3_o_singura_data() -> None:
    assert [s.titlu for s in SCENARII] == _scenarii_din_document()
    assert len({s.cod for s in SCENARII}) == len(SCENARII)
    assert all(s.teste for s in SCENARII)


def test_fiecare_nod_din_catalog_exista() -> None:
    for nod in noduri():
        fisier, functie = nod.split("::")
        cale = ROOT / fisier
        assert cale.is_file(), nod
        nume = {n.name for n in ast.walk(ast.parse(cale.read_text())) if isinstance(n, ast.FunctionDef)}
        assert functie in nume, nod


def test_raportul_pe_scenarii_cere_toate_testele_trecute(tmp_path: Path) -> None:
    from tests.avarie import raport

    [prim, *rest] = SCENARII[0].teste
    f, n = prim.split("::")
    cazuri = f'<testcase file="{f}" name="{n}"/>' + "".join(
        f'<testcase file="{t.split("::")[0]}" name="{t.split("::")[1]}"><skipped/></testcase>' for t in rest
    )
    (tmp_path / "j.xml").write_text(f"<testsuites><testsuite>{cazuri}</testsuite></testsuites>")
    r = raport.raport(tmp_path / "j.xml")
    s0 = r["scenarii"][0]  # type: ignore[index]
    assert s0["teste"][prim] == "trecut" and not s0["trecut"], "un test sărit nu e o dovadă"
    assert r["trecute"] == 0 and raport.main([str(tmp_path / "j.xml")]) == 1
