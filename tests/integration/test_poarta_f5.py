"""Poarta F5 (docs/23 §23.8, docs/09 §9.9): cel puțin 95% din materialele intenționat greșite sunt blocate și cel mult 10% din
cele bune sunt respinse pe nedrept — cu validatorii DETERMINIȘTI (V0–V2), judecătorii (V3 / V4) opriți, pe seturile de aur
ÎNGHEȚATE (`evaluare/aur/`). Niciun model nu e chemat: orice apel la gateway pică testul. Cu judecători reali (și cu pașii V2
care cer vectori: G4@V2, G7@V2) poarta se măsoară la migrare."""

from typing import Any

import pytest

from app import gateway
from app.validare.banc import executie, scoruri, seturi
from tests.conftest import BazaTest

pytestmark = pytest.mark.db


def _interzis(*_a: Any, **_k: Any) -> Any:
    raise AssertionError("poarta F5 se măsoară fără niciun model (judecătorii sunt opriți)")


def test_poarta_f5_pe_seturile_inghetate(baza: BazaTest, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway, "apeleaza", _interzis)
    monkeypatch.setattr(gateway, "vectorizeaza", _interzis)
    assert seturi.inghetat() == seturi.amprente_baza(), "seturile nu au fost schimbate ca să treacă poarta"
    s = seturi.incarca()
    sc = executie.ruleaza(s)  # fără exemple promovate: doar seturile din depozit
    p = sc["poarta"]
    assert p["rele_total"] == len(s.rele) >= 100 and p["bune_total"] == len(s.bune) >= 60
    assert p["rata_blocare"] >= scoruri.PRAG_BLOCARE == 0.95, sc["rele"]["pe_validator"]
    assert p["rata_respingere_pe_nedrept"] <= scoruri.PRAG_RESPINGERE_NEDREAPTA == 0.10, sc["bune"]
    assert p["trece"] is True
    # fiecare validator vizat își prinde materialele greșite (nu doar cascada în ansamblu)
    for g, d in sc["rele"]["pe_validator"].items():
        assert d["rata_blocare"] >= 0.95, (g, d["scapate"])
    assert sc["omise"] == ["G4@V2", "G7@V2"]
