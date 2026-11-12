"""F3.9 (b) — marcarea conținutului extern și detecția euristică de injecții, pe colecția de atacuri cunoscute."""

import base64
import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.gateway import extern, injectii


def _incarca() -> list[dict[str, Any]]:
    atacuri = json.loads((Path(__file__).parents[1] / "fixtures" / "gateway" / "injectii.json").read_text())[
        "atacuri"
    ]
    for a in atacuri:
        if a.get("base64"):  # codificat la rulare: un șir base64 în repo ar fi semnalat ca secret
            a["text"] = base64.b64encode(a["text"].encode()).decode()
    return atacuri  # type: ignore[no-any-return]


ATACURI = _incarca()


def test_textul_este_impachetat_cu_delimitatori_si_id_aleator() -> None:
    a, b = (
        extern.marcheaza_extern("salut", sursa="comentariu"),
        extern.marcheaza_extern("salut", sursa="comentariu"),
    )
    [(sursa, corp)] = extern.blocuri(a)
    assert (sursa, corp) == ("comentariu", "salut")
    assert re.search(r"id=([a-z]{12})>>>", a).group(1) != re.search(r"id=([a-z]{12})>>>", b).group(1)  # type: ignore[union-attr]


@pytest.mark.parametrize("atac", ATACURI, ids=[a["id"] for a in ATACURI])
def test_niciun_atac_nu_poate_inchide_sau_deschide_blocul(atac: dict[str, Any]) -> None:
    marcat = extern.marcheaza_extern(atac["text"], sursa=atac["sursa"])
    assert marcat.count("<<<DATE_EXTERNE") == 1 and marcat.count("<<<SFARSIT_DATE_EXTERNE") == 1
    assert marcat.count(">>>") == 2  # doar ale noastre
    [(_, corp)] = extern.blocuri(marcat)  # tot textul, și numai el, e în interiorul unui singur bloc
    assert "<<<" not in corp and ">>>" not in corp
    assert not extern.INVIZIBILE.search(corp)


@pytest.mark.parametrize("atac", [a for a in ATACURI if a["detectabil"]], ids=lambda a: a["id"])
def test_atacurile_detectabile_dau_semnal_cu_codul_asteptat(atac: dict[str, Any]) -> None:
    marcat = extern.marcheaza_extern(atac["text"], sursa=atac["sursa"])
    [(sursa, corp)] = extern.blocuri(marcat)
    coduri = {s.cod for s in injectii.cauta(corp, sursa)}
    assert atac["cod"] in coduri, (atac["id"], coduri)


def test_textul_inofensiv_si_atacurile_nedetectabile_nu_dau_semnal_si_asta_e_spus_explicit() -> None:
    # Euristica NU prinde parafraze, alte limbi, codificări: apărarea reală e marcarea + schema.
    for a in (x for x in ATACURI if not x["detectabil"]):
        assert injectii.cauta(a["text"], a["sursa"]) == [], a["id"]


def test_sursa_trebuie_sa_fie_un_cuvant_si_textul_prea_lung_se_trunchiaza() -> None:
    with pytest.raises(ValueError):
        extern.marcheaza_extern("x", sursa="Pagina web!")
    lung = extern.marcheaza_extern("a" * 100, sursa="pagina", max_caractere=10)
    assert "[…text trunchiat]" in lung and "a" * 11 not in lung
