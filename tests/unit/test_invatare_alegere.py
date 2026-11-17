"""F11.3 — alegerea adaptivă pe date SIMULATE. „Gata când”: alegerea hook-urilor și a sloturilor se schimbă
vizibil. Mediul simulat are rate adevărate pe variantă; banditul nu le știe și le învață din recompense."""

# ruff: noqa: S311
import random

import pytest

from app.continut import scriere
from app.continut.scriere import HookPropus
from app.invatare import alegere as a
from app.invatare.alegere import Observatie

ADEVAR = {"intrebare": 0.09, "cifra": 0.03, "poveste": 0.02, "rezultat": 0.04}


def simuleaza(optiuni: dict[str, float], runde: int, samanta: int = 7) -> tuple[list[str], list[Observatie]]:
    """Fiecare rundă: banditul alege, mediul răspunde cu rata adevărată ± zgomot; alegerile se țin în ordine."""
    rng, mediu = random.Random(samanta), random.Random(samanta + 1)
    obs: list[Observatie] = []
    alese: list[str] = []
    for _ in range(runde):
        v = a.alege(a.stare(list(optiuni), obs), rng).valoare
        alese.append(v)
        obs.append(Observatie(v, max(0.0, mediu.gauss(optiuni[v], optiuni[v] / 4)), 0.0))
    return alese, obs


def test_alegerea_hookurilor_se_schimba_vizibil_spre_ce_merge() -> None:
    alese, obs = simuleaza(ADEVAR, 400)
    inceput, sfarsit = alese[:40], alese[-100:]
    cota_la_inceput = inceput.count("intrebare") / len(inceput)
    cota_la_sfarsit = sfarsit.count("intrebare") / len(sfarsit)
    assert cota_la_sfarsit > 0.5 and cota_la_sfarsit > cota_la_inceput + 0.2, (
        cota_la_inceput,
        cota_la_sfarsit,
    )
    assert set(alese[-100:]) > {"intrebare"}, "explorarea continuă: nu rămâne o singură variantă"
    stare = {v.valoare: v for v in a.stare(list(ADEVAR), obs)}
    assert max(stare.values(), key=lambda v: v.medie).valoare == "intrebare"
    assert stare["intrebare"].de_incredere and abs(stare["intrebare"].medie - 0.09) < 0.02


def test_alegerea_sloturilor_se_schimba_la_fel() -> None:
    sloturi = {"marți, ora 09": 0.03, "joi, ora 18": 0.08, "sâmbătă, ora 11": 0.04}
    alese, _ = simuleaza(sloturi, 300, samanta=21)
    assert alese[-100:].count("joi, ora 18") > 50 > alese[:30].count("joi, ora 18")


def test_explorarea_minima_este_garantata() -> None:
    v = a.stare(
        ["buna", "slaba"], [Observatie("buna", 0.5, 0.0)] * 200 + [Observatie("slaba", 0.0, 0.0)] * 200
    )
    rng = random.Random(3)
    alese = [a.alege(v, rng).valoare for _ in range(4000)]
    cota_slaba = alese.count("slaba") / len(alese)
    assert 0.05 < cota_slaba < 0.12, "la egalitate de testare, explorarea (15%) se împarte între variante"
    # o variantă nouă, netestată, primește toată explorarea
    cu_noua = a.stare(
        ["buna", "slaba", "noua"],
        [Observatie("buna", 0.5, 0.0)] * 200 + [Observatie("slaba", 0.0, 0.0)] * 200,
    )
    alese = [a.alege(cu_noua, random.Random(i)).valoare for i in range(2000)]
    assert alese.count("noua") / len(alese) >= 0.15
    with pytest.raises(ValueError):
        a.alege([], rng)


def test_pornirea_la_rece_si_uitarea_in_90_de_zile() -> None:
    [noua] = a.stare(["noua"], [])
    assert noua.medie == pytest.approx(a.MEDIE_NISA) and noua.publicari == 0 and not noua.de_incredere
    assert a.pondere(0) == 1.0 and a.pondere(45) == 0.5 and a.pondere(90) == 0.0 and a.pondere(400) == 0.0
    vechi = [Observatie("x", 0.5, 89.0)] * 20
    recent = [Observatie("x", 0.02, 1.0)] * 20
    [v] = a.stare(["x"], vechi + recent)
    assert v.medie < 0.05, "rezultatele vechi cântăresc puțin față de cele recente"
    [expirat] = a.stare(["x"], [Observatie("x", 0.9, 120.0)] * 50)
    assert expirat.publicari == 0 and expirat.medie == pytest.approx(a.MEDIE_NISA)


def test_preferinta_doar_departajeaza_hookurile_de_calitate_apropiata() -> None:
    brief: dict[str, object] = {"subiect": "cafea proaspăt prăjită", "fapte_permise": []}
    bune = [
        HookPropus(text="De ce contează cafeaua proaspăt prăjită?", tipar="intrebare"),
        HookPropus(text="Greșeala cu cafeaua proaspăt prăjită", tipar="greseala"),
    ]
    assert scriere.alege(bune, brief) == 0
    assert scriere.alege(bune, brief, tipar_preferat="greseala") == 1, (
        "la calitate egală, câștigă tiparul preferat"
    )
    assert scriere.alege(bune, brief, tipar_preferat="poveste") == 0, (
        "tipar absent: alegerea rămâne cea veche"
    )
    cu_cifra_fara_fapt = [bune[0], HookPropus(text="97% aleg cafea proaspăt prăjită", tipar="cifra")]
    assert scriere.alege(cu_cifra_fara_fapt, brief, tipar_preferat="cifra") == 0, (
        "preferința nu bate calitatea"
    )
