"""F15.4: ciornele juridice din docs/juridic/ și paginile publice generate din ele, marcate până la avocat."""

from pathlib import Path

import pytest

from app.site import pagini

ROOT = Path(__file__).resolve().parents[2]
CERUTE = {
    "contract-servicii.md",
    "acord-prelucrare.md",
    "termeni.md",
    "confidentialitate.md",
    "cookie-uri.md",
}


def test_ciornele_cerute_exista_si_sunt_marcate_pentru_avocat() -> None:
    fisiere = {p.name for p in pagini.DIR_JURIDIC.glob("*.md")} - {"README.md"}
    assert fisiere == CERUTE == {f for f, _ in pagini.DOCUMENTE_JURIDICE}
    for f, cale in pagini.DOCUMENTE_JURIDICE:
        p = pagini.TOATE[cale]
        assert p.extra.get("ciorna") == pagini.CIORNA and "revizuirea avocatului" in pagini.CIORNA, f
        assert len(p.sectiuni) >= 3 and all(s.paragrafe or s.lista for s in p.sectiuni), f


def test_contractul_si_dpa_acopera_ce_cere_21() -> None:
    contract = " ".join(" ".join(s.paragrafe + s.lista) for s in pagini.TOATE["legal/contract"].sectiuni)
    for nisa in ("politică", "jocuri de noroc", "adulți", "promisiuni medicale", "scheme financiare"):
        assert nisa in contract, nisa  # §21.12: lista de nișe refuzate e scrisă în contract
    assert "drept de autor" in contract and "L1" in contract  # §21.11, §25.7
    dpa = pagini.TOATE["legal/acord-prelucrare"]
    assert {"Roluri", "Subîmputerniciți"} <= {s.titlu for s in dpa.sectiuni}


@pytest.mark.parametrize("cale", ["legal/termeni", "legal/stergere-date"])
def test_paginile_legale_raman_in_afara_meniului(cale: str) -> None:
    assert not pagini.TOATE[cale].in_meniu


def test_imaginea_contine_ciornele_din_care_se_genereaza_paginile() -> None:
    assert "COPY docs/juridic ./docs/juridic" in (ROOT / "Dockerfile").read_text()
    assert "!docs/juridic" in (ROOT / ".dockerignore").read_text().splitlines()


def test_o_pagina_semnata_de_avocat_nu_mai_are_marcajul(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "x.md").write_text("# T\ndescriere: d\n\n## S\nText.\n- unu\n", encoding="utf-8")
    monkeypatch.setattr(pagini, "DIR_JURIDIC", tmp_path)
    p = pagini.din_juridic("x.md", "legal/x")
    assert p.extra == {} and p.sectiuni[0].paragrafe == ("Text.",) and p.sectiuni[0].lista == ("unu",)
