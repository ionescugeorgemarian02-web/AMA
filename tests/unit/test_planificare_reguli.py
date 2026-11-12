"""F3.11 — nucleul pur al planificatorului de capacitate: ce încape azi, ce se amână, ce rămâne neatins."""

import datetime as dt
import uuid

from app.operare.motor import Prioritate
from app.planificare.reguli import Capacitate, Cost, Decizie, Element, planifica, prioritate, protejat

ACUM = dt.datetime(2026, 11, 12, 8, 0, tzinfo=dt.UTC)
PRAG = dt.timedelta(hours=48)
POSTARE = Cost({"creatie": {"apeluri": 2, "tokeni": 1000}})


def el(zile: float | None, cost: Cost = POSTARE, n: int = 0) -> Element:
    termen = None if zile is None else ACUM + dt.timedelta(days=zile)
    return Element(uuid.UUID(int=n + 1), uuid.UUID(int=99), "postare", termen, cost)


def decizii(rez, elemente):  # type: ignore[no-untyped-def]
    return {e.id: next(v.decizie for v in rez.verdicte if v.element.id == e.id) for e in elemente}


def test_prioritatea_si_protectia_dupa_termen() -> None:
    assert prioritate(ACUM + dt.timedelta(hours=10), ACUM) is Prioritate.P0
    assert prioritate(ACUM - dt.timedelta(hours=1), ACUM) is Prioritate.P0  # termen depășit
    assert (
        prioritate(ACUM + dt.timedelta(days=3), ACUM) is Prioritate.P1
        and prioritate(None, ACUM) is Prioritate.P1
    )
    assert protejat(ACUM + dt.timedelta(hours=47), ACUM, PRAG) and not protejat(
        ACUM + dt.timedelta(hours=49), ACUM, PRAG
    )
    assert not protejat(None, ACUM, PRAG)


def test_cand_totul_incape_nu_se_amana_nimic() -> None:
    elemente = [el(5, n=i) for i in range(4)]
    rez = planifica(elemente, Capacitate({"creatie": 8}, {"creatie": None}, 0), ACUM, prag_apropiat=PRAG)
    assert not rez.depasiri and not rez.cu_decizia(Decizie.AMANAT)


def test_se_amana_termenul_cel_mai_indepartat_intai_si_cel_apropiat_ramane() -> None:
    elemente = [el(1, n=1), el(10, n=2), el(4, n=3), el(30, n=4), el(None, n=5), el(7, n=6)]
    # capacitate pentru 3 livrabile (6 apeluri): rămân cele cu termenele 1, 4, 7
    rez = planifica(elemente, Capacitate({"creatie": 6}, {"creatie": None}, 0), ACUM, prag_apropiat=PRAG)
    d = decizii(rez, elemente)
    amanate = {e.termen_la and (e.termen_la - ACUM).days for e in elemente if d[e.id] is Decizie.AMANAT}
    assert amanate == {10, 30, None}  # termen îndepărtat și fără termen
    assert d[elemente[0].id] is Decizie.PROTEJAT  # termenul de o zi: neatins
    assert d[elemente[2].id] is Decizie.PASTRAT and d[elemente[5].id] is Decizie.PASTRAT
    assert rez.depasiri == (("apeluri", "creatie"),) and not rez.peste_capacitate


def test_livrabilele_cu_termen_apropiat_si_p0_nu_se_ating_chiar_peste_capacitate() -> None:
    elemente = [el(0.3, n=1), el(1.5, n=2), el(1.9, n=3), el(6, n=4)]
    rez = planifica(elemente, Capacitate({"creatie": 2}, {"creatie": None}, 0), ACUM, prag_apropiat=PRAG)
    d = decizii(rez, elemente)
    assert [d[e.id] for e in elemente] == [Decizie.PROTEJAT] * 3 + [Decizie.AMANAT]
    assert rez.peste_capacitate == (("apeluri", "creatie"),)  # planul rămâne peste capacitate: alerta o spune


def test_se_amana_doar_ce_ajuta_o_axa_depasita() -> None:
    video = Cost({"creatie": {"apeluri": 1, "tokeni": 10}}, minute_cpu=30.0)
    simplu = Cost({"creatie": {"apeluri": 1, "tokeni": 10}})
    elemente = [el(20, video, 1), el(15, simplu, 2), el(12, video, 3)]
    # apelurile încap, CPU nu: se amână videoclipul cel mai îndepărtat, nu postarea simplă (care nu ajută)
    rez = planifica(elemente, Capacitate({"creatie": 10}, {"creatie": None}, 45.0), ACUM, prag_apropiat=PRAG)
    d = decizii(rez, elemente)
    assert d[elemente[0].id] is Decizie.AMANAT and d[elemente[1].id] is Decizie.PASTRAT
    assert d[elemente[2].id] is Decizie.PASTRAT and rez.depasiri == (("cpu", ""),)


def test_profil_fara_capacitate_amana_tot_ce_se_poate_iar_fara_limita_nu_amana_nimic() -> None:
    elemente = [el(10, n=1), el(20, n=2)]
    assert (
        len(planifica(elemente, Capacitate({}, {}, 0), ACUM, prag_apropiat=PRAG).cu_decizia(Decizie.AMANAT))
        == 2
    )
    liber = Capacitate({"creatie": None}, {"creatie": None}, 0)
    assert not planifica(elemente, liber, ACUM, prag_apropiat=PRAG).cu_decizia(Decizie.AMANAT)


def test_rezultatul_este_determinist() -> None:
    elemente = [el(9, n=i) for i in range(1, 7)]  # același termen
    cap = Capacitate({"creatie": 6}, {"creatie": None}, 0)
    a = planifica(elemente, cap, ACUM, prag_apropiat=PRAG)
    b = planifica(list(reversed(elemente)), cap, ACUM, prag_apropiat=PRAG)
    assert {v.element.id for v in a.cu_decizia(Decizie.AMANAT)} == {
        v.element.id for v in b.cu_decizia(Decizie.AMANAT)
    }
