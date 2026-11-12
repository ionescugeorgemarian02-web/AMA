"""F2.8 — regulile cererilor de aprobare (nucleu pur): stări, cine decide, termene."""

import datetime as dt
import itertools

import pytest

from app.conturi.roluri import Rol
from app.productie.reguli_aprobare import (
    MOTIVE_RESPINGERE,
    TRANZITII,
    Decident,
    StareAprobare,
    TermenTrecut,
    calculeaza_termene,
    este_finala,
    motiv_valid,
    poate_decide,
)

T0 = dt.datetime(2026, 11, 12, 9, 0, tzinfo=dt.UTC)
PERMISE = {
    (StareAprobare.IN_ASTEPTARE, StareAprobare.APROBAT),
    (StareAprobare.IN_ASTEPTARE, StareAprobare.RESPINS),
    (StareAprobare.IN_ASTEPTARE, StareAprobare.EXPIRAT),
    (StareAprobare.IN_ASTEPTARE, StareAprobare.ANULAT),
}


@pytest.mark.parametrize(("din", "la"), list(itertools.product(StareAprobare, StareAprobare)))
def test_doar_din_in_asteptare_se_iese_si_nimic_nu_se_redeschide(
    din: StareAprobare, la: StareAprobare
) -> None:
    assert (la in TRANZITII[din]) is ((din, la) in PERMISE)


def test_starile_finale() -> None:
    assert [s for s in StareAprobare if este_finala(s)] == [
        StareAprobare.APROBAT,
        StareAprobare.RESPINS,
        StareAprobare.EXPIRAT,
        StareAprobare.ANULAT,
    ]


@pytest.mark.parametrize(
    ("rol", "decident", "asteptat"),
    [
        (Rol.PROPRIETAR, Decident.OPERATOR, True),
        (Rol.OPERATOR, Decident.OPERATOR, True),
        (Rol.ANALIST, Decident.OPERATOR, False),
        (Rol.CLIENT_TITULAR, Decident.OPERATOR, False),
        (Rol.CLIENT_APROBATOR, Decident.OPERATOR, False),
        (Rol.CLIENT_VIZITATOR, Decident.OPERATOR, False),
        (Rol.CLIENT_TITULAR, Decident.CLIENT, True),
        (Rol.CLIENT_APROBATOR, Decident.CLIENT, True),
        (Rol.CLIENT_VIZITATOR, Decident.CLIENT, False),
        (Rol.PROPRIETAR, Decident.CLIENT, False),
        (Rol.OPERATOR, Decident.CLIENT, False),
        (Rol.ANALIST, Decident.CLIENT, False),
    ],
)
def test_cine_poate_decide(rol: Rol, decident: Decident, asteptat: bool) -> None:
    assert poate_decide(rol, decident) is asteptat


def test_rol_necunoscut_nu_poate_decide() -> None:
    assert not poate_decide("zeu", Decident.OPERATOR) and not poate_decide("", Decident.CLIENT)


def test_termenul_implicit_este_de_48_de_ore_cu_reamintire_la_24_de_ore() -> None:
    termen, reamintire = calculeaza_termene(T0, None, termen_ore=48, reamintire_ore=24)
    assert termen == T0 + dt.timedelta(hours=48) and reamintire == T0 + dt.timedelta(hours=24)


def test_termenul_nu_depaseste_slotul_livrabilului() -> None:
    slot = T0 + dt.timedelta(hours=10)
    termen, reamintire = calculeaza_termene(T0, slot, termen_ore=48, reamintire_ore=24)
    assert termen == slot
    assert reamintire == T0 + dt.timedelta(hours=5), "interval scurt: reamintirea la jumătate"
    termen2, _ = calculeaza_termene(T0, T0 + dt.timedelta(days=9), termen_ore=48, reamintire_ore=24)
    assert termen2 == T0 + dt.timedelta(hours=48), "un slot îndepărtat nu prelungește termenul"


@pytest.mark.parametrize("slot", [T0, T0 - dt.timedelta(hours=1)])
def test_slot_trecut_nu_permite_cererea(slot: dt.datetime) -> None:
    with pytest.raises(TermenTrecut):
        calculeaza_termene(T0, slot, termen_ore=48, reamintire_ore=24)


def test_reamintirea_vine_intotdeauna_inainte_de_termen_si_dupa_creare() -> None:
    for ore in (1, 2, 24, 48, 100):
        termen, reamintire = calculeaza_termene(T0, None, termen_ore=ore, reamintire_ore=24)
        assert T0 < reamintire < termen


def test_motivele_standard_din_18_3_si_validarea_motivului() -> None:
    assert len(MOTIVE_RESPINGERE) == 8 and "altceva" in MOTIVE_RESPINGERE
    assert motiv_valid("hook slab") and not motiv_valid("  a ") and not motiv_valid("x" * 301)
