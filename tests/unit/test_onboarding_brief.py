"""F4.4 — nucleul pur al onboardingului: interviul ca date și validarea de completitudine STRICTĂ a brieful."""

import copy
from typing import Any

from app.onboarding import brief, interviu
from app.onboarding.completare import CampPropus, verifica_camp


def brief_complet() -> dict[str, Any]:
    return {
        camp: {
            "valoare": f"Valoare suficient de lungă și concretă pentru {camp}",
            "surse": [{"tip": "raspuns", "ref": "r1", "citat": "Valoare suficient"}],
        }
        for camp in brief.CAMPURI
    }


def test_interviul_acopera_toate_campurile_brieful_si_este_consistent() -> None:
    assert interviu.valideaza() == []
    assert {q.camp for q in interviu.intrebari()} == set(brief.CAMPURI)
    # 19.3: ce vinde, cui, la ce preț, de ce, obiecții, concurenți, ce a încercat, interdicții, ton, obiectiv
    assert len(interviu.INTERVIU) >= 4 and len(interviu.intrebari()) == len(brief.CAMPURI) == 11


def test_un_brief_complet_nu_are_probleme() -> None:
    assert brief.lipsuri(brief_complet()) == [] and brief.este_complet(brief_complet())


def test_fiecare_camp_lipsa_gol_substitut_scurt_sau_fara_sursa_este_o_problema() -> None:
    for camp, nume in brief.CAMPURI.items():
        lipsa = brief_complet()
        del lipsa[camp]
        assert brief.lipsuri(lipsa) == [f"{nume}: lipsește"]
        for gol in ("", "   ", "-", "n/a", "Nu știu", "...", "TBD"):
            v = brief_complet()
            v[camp]["valoare"] = gol
            assert len(brief.lipsuri(v)) == 1 and brief.lipsuri(v)[0].startswith(f"{nume}: gol"), (camp, gol)
        scurt = brief_complet()
        scurt[camp]["valoare"] = "x" * 3
        assert "prea scurt" in brief.lipsuri(scurt)[0]
        fara = brief_complet()
        fara[camp]["surse"] = []
        assert brief.lipsuri(fara) == [f"{nume}: fără sursă"]


def test_un_brief_gol_are_toate_problemele_si_numaratoarea_campurilor_complete() -> None:
    assert len(brief.lipsuri({})) == len(brief.CAMPURI) and brief.numar_campuri_complete({}) == 0
    b = brief_complet()
    b["ton_dorit"]["valoare"] = ""
    assert brief.numar_campuri_complete(b) == len(brief.CAMPURI) - 1


def test_schema_nu_accepta_campuri_in_plus() -> None:
    import pydantic
    import pytest

    with pytest.raises(pydantic.ValidationError):
        brief.BriefClient.model_validate(
            {**copy.deepcopy(brief_complet()), "extra": {"valoare": "x", "surse": []}}
        )


def test_verificatorul_de_campuri_respinge_citate_inventate_surse_neoferite_si_campuri_straine() -> None:
    r = {"r1": "Cafea de specialitate în boabe și abonamente lunare"}
    p = {"p1": "Prăjim în loturi mici, de maximum 12 kilograme"}
    ok = CampPropus(
        camp="ce_vinde",
        valoare="Cafea",
        sursa_tip="raspuns",
        sursa_ref="r1",
        citat="Cafea de specialitate în boabe",
    )
    assert verifica_camp(ok, r, p) is None
    de_la_pasaj = ok.model_copy(
        update={"sursa_tip": "pasaj", "sursa_ref": "p1", "citat": "loturi mici, de maximum 12"}
    )
    assert verifica_camp(de_la_pasaj, r, p) is None
    assert (
        verifica_camp(ok.model_copy(update={"citat": "un citat inventat de model"}), r, p) == "citat_negasit"
    )
    assert verifica_camp(ok.model_copy(update={"sursa_ref": "r9"}), r, p) == "sursa_neoferita"
    assert (
        verifica_camp(ok.model_copy(update={"sursa_tip": "pasaj"}), r, p) == "sursa_neoferita"
    )  # r1 nu e pasaj
    assert verifica_camp(ok.model_copy(update={"camp": "altceva"}), r, p) == "camp_necunoscut"
    assert verifica_camp(ok.model_copy(update={"valoare": "  "}), r, p) == "valoare_goala"
