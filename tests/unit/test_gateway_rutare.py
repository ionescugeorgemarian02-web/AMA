"""F3.4 — nucleele pure ale rutării: eligibilitatea, ordinea, lanțurile, întrerupătorul. Fără bază, fără rețea."""

import datetime as dt
import uuid
from typing import Any

import pytest

from app.gateway import intrerupator, profiluri
from app.gateway.candidat import Candidat
from app.gateway.cote import LimiteCota
from app.gateway.intrerupator import StareSanatate
from app.gateway.profiluri import Profil
from app.gateway.rutare import Cerinte, Motiv, alege, motiv_excludere
from app.operare.motor import Prioritate

ACUM = dt.datetime(2026, 11, 12, 12, 0, tzinfo=dt.UTC)


def cand(furnizor: str = "a", ident: str = "m", nivel: str = "T2", **kw: Any) -> Candidat:
    valori: dict[str, Any] = {
        "model_id": uuid.uuid4(), "furnizor_id": uuid.uuid4(), "furnizor": furnizor, "tip_api": "openai_compat",
        "url_baza": "https://exemplu.test", "parametri": {}, "cheie_env": "AMA_CHEIE_X", "identificator": ident,
        "nivel": nivel, "capabilitati": frozenset(), "limite_model": LimiteCota(), "limite_furnizor": LimiteCota(),
        "reset_zi_ora": 0, "stare_furnizor": "activ", "model_activ": True, "platit": False,
        "uz_comercial": True, "antrenare_pe_date": False,
    }  # fmt: skip
    valori.update(kw)
    return Candidat(**valori)


def profil(lant: tuple[str, ...], nivel_min: str = "T2", la_epuizare: str = "amana", **kw: Any) -> Profil:
    return Profil(
        nume=kw.pop("nume", "proba"), eticheta="Probă", descriere="", nivel_min=nivel_min,
        capabilitati=kw.pop("capabilitati", frozenset()), lant=lant, la_epuizare=la_epuizare, **kw,
    )  # fmt: skip


def cer(**kw: Any) -> Cerinte:
    return Cerinte(prioritate=kw.pop("prioritate", Prioritate.P1), acum=ACUM, **kw)


def coduri(c: tuple[Candidat, ...]) -> list[str]:
    return [x.cod for x in c]


def test_profilurile_din_8_2_sunt_date_coerente() -> None:
    assert profiluri.valideaza() == []
    pe_nume = {p.nume: p for p in profiluri.PROFILURI}
    assert set(pe_nume) == {"clasificare", "rescriere", "creatie", "judecata", "strategie", "consiliu"}
    # tabelul din 8.2: ce se întâmplă când lipsește cota
    assert pe_nume["clasificare"].la_epuizare == "degradeaza" and pe_nume["clasificare"].nivel_min == "T1"
    assert pe_nume["rescriere"].la_epuizare == "degradeaza" and pe_nume["rescriere"].verificare_in_plus
    assert pe_nume["creatie"].la_epuizare == "amana" and pe_nume["judecata"].la_epuizare == "amana"
    assert pe_nume["strategie"].la_epuizare == "amana" and pe_nume["strategie"].nivel_min == "T3"
    assert pe_nume["strategie"].lant_degradare == ()  # niciodată un model mai slab
    assert pe_nume["consiliu"].la_epuizare == "amana_sau_provizoriu" and pe_nume["consiliu"].nivel_min == "T4"
    assert pe_nume["consiliu"].lant_degradare == ("nivel:T3",)  # „T3 cu eticheta provizoriu”


def test_lantul_decide_ordinea_iar_modelele_necunoscute_se_sar() -> None:
    a, b, c = cand("f1", "x"), cand("f2", "y"), cand("f3", "z")
    p = profil(("f2/y", "f9/nu-exista", "f3/z", "f1/x"))
    sel = alege(p, [a, b, c], cer())
    assert coduri(sel.principal) == ["f2/y", "f3/z", "f1/x"]


def test_scorul_pe_profil_trece_inaintea_pozitiei_in_lant() -> None:
    a, b = cand("f1", "x", scor={"proba": 0.4}), cand("f2", "y", scor={"proba": 0.9})
    assert coduri(alege(profil(("f1/x", "f2/y")), [a, b], cer()).principal) == ["f2/y", "f1/x"]
    # un scor pe ALT profil nu contează; egalitatea se rezolvă după lanț
    a2, b2 = cand("f1", "x", scor={"altul": 1.0}), cand("f2", "y")
    assert coduri(alege(profil(("f1/x", "f2/y")), [a2, b2], cer()).principal) == ["f1/x", "f2/y"]


def test_nivelul_minim_se_aplica_lantului_principal_niciodata_un_model_mai_slab() -> None:
    mic, bun = cand("f1", "mic", nivel="T2"), cand("f2", "bun", nivel="T3")
    sel = alege(profil(("f1/mic", "f2/bun"), nivel_min="T3"), [mic, bun], cer())
    assert coduri(sel.principal) == ["f2/bun"]
    assert sel.excluse == (("f1/mic", Motiv.NIVEL),)


def test_lantul_de_degradare_poate_cobori_sub_nivelul_minim_si_expandeaza_nivelurile() -> None:
    principal, local1, local2, altul = (
        cand("f1", "p", nivel="T2"), cand("loc", "a", nivel="local"), cand("loc", "b", nivel="local"), cand("f2", "q", nivel="T1"),
    )  # fmt: skip
    p = profil(("f1/p",), nivel_min="T2", la_epuizare="degradeaza", lant_degradare=("nivel:local", "f2/q"))
    sel = alege(p, [principal, local1, local2, altul], cer())
    assert coduri(sel.degradare) == ["loc/a", "loc/b", "f2/q"]
    assert (
        alege(p, [principal], cer()).degradare == ()
    )  # modelul local nu există încă (F3.5): profilul nu se strică


@pytest.mark.parametrize(
    ("campuri", "cerinte", "motiv"),
    [
        ({"stare_furnizor": "inactiv"}, {}, Motiv.FURNIZOR_OPRIT),
        ({"stare_furnizor": "pauza"}, {}, Motiv.FURNIZOR_OPRIT),
        ({"model_activ": False}, {}, Motiv.MODEL_OPRIT),
        ({}, {"chei_configurate": frozenset({"altul"})}, Motiv.FARA_CHEIE),
        ({"uz_comercial": False}, {}, Motiv.UZ_COMERCIAL),
        ({"uz_comercial": None}, {}, Motiv.UZ_COMERCIAL),
        ({"antrenare_pe_date": True}, {"date_confidentiale": True}, Motiv.ANTRENARE_PE_DATE),
        ({"antrenare_pe_date": None}, {"date_confidentiale": True}, Motiv.ANTRENARE_PE_DATE),
        ({}, {"capabilitati": frozenset({"viziune"})}, Motiv.CAPABILITATE),
        ({"nivel": "T1"}, {}, Motiv.NIVEL),
        ({"nivel": "T4"}, {"prioritate": Prioritate.P0}, Motiv.T4_CALE_CRITICA),
        ({"nivel": "T4"}, {"prioritate": Prioritate.P1}, Motiv.T4_CALE_CRITICA),
        ({"platit": True}, {"apeluri_platite_oprite": True}, Motiv.APELURI_PLATITE),
        ({}, {"alt_model_decat": "a/m"}, Motiv.ACELASI_MODEL),
        ({}, {"sanatate": {"a": StareSanatate(3, ACUM + dt.timedelta(seconds=30))}}, Motiv.INTRERUPATOR),
    ],
)
def test_fiecare_motiv_de_excludere(campuri: dict[str, Any], cerinte: dict[str, Any], motiv: Motiv) -> None:
    c = cand(**campuri)
    assert motiv_excludere(c, profil(("a/m",)), cer(**cerinte), degradare=False) is motiv


@pytest.mark.parametrize(
    ("campuri", "cerinte"),
    [
        ({}, {}),
        ({"nivel": "T4"}, {"prioritate": Prioritate.P2}),
        ({"nivel": "T4"}, {"prioritate": Prioritate.P3}),
        ({"platit": True}, {}),
        ({"antrenare_pe_date": None}, {}),  # fără date confidențiale, antrenarea necunoscută nu contează
        ({}, {"sanatate": {"a": StareSanatate(3, ACUM - dt.timedelta(seconds=1))}}),  # pauza a trecut: proba
        ({}, {"alt_model_decat": "a/altul"}),
        ({"capabilitati": frozenset({"viziune", "unelte"})}, {"capabilitati": frozenset({"viziune"})}),
    ],
)
def test_modelul_ramane_eligibil(campuri: dict[str, Any], cerinte: dict[str, Any]) -> None:
    c = cand(**campuri)
    assert motiv_excludere(c, profil(("a/m",), nivel_min="T2"), cer(**cerinte), degradare=False) is None


def test_t4_ramane_in_afara_caii_critice_adica_numai_la_p2_si_p3() -> None:
    opus = cand("anthropic", "opus", nivel="T4", platit=True)
    p = profil(("anthropic/opus",), nivel_min="T4")
    for pr in (Prioritate.P0, Prioritate.P1):
        sel = alege(p, [opus], cer(prioritate=pr))
        assert sel.principal == () and sel.motive() == {Motiv.T4_CALE_CRITICA}
    for pr in (Prioritate.P2, Prioritate.P3):
        assert coduri(alege(p, [opus], cer(prioritate=pr)).principal) == ["anthropic/opus"]


def test_oprirea_apelurilor_platite_scoate_doar_modelele_platite() -> None:
    gratis, platit = cand("f1", "g"), cand("f2", "p", platit=True)
    sel = alege(profil(("f1/g", "f2/p")), [gratis, platit], cer(apeluri_platite_oprite=True))
    assert coduri(sel.principal) == ["f1/g"] and sel.excluse == (("f2/p", Motiv.APELURI_PLATITE),)


def test_profilul_cere_capabilitatile_lui() -> None:
    fara, cu = cand("f1", "x"), cand("f2", "y", capabilitati=frozenset({"iesire_structurata"}))
    p = profil(("f1/x", "f2/y"), capabilitati=frozenset({"iesire_structurata"}))
    assert coduri(alege(p, [fara, cu], cer()).principal) == ["f2/y"]


# --- întrerupătorul (nucleu pur)


def test_intrerupatorul_se_deschide_la_prag_si_se_inchide_la_succes() -> None:
    s = StareSanatate()
    for n in (1, 2):
        s = intrerupator.dupa_esec(s, ACUM, prag=3, pauza_sec=120)
        assert s.erori_consecutive == n and not intrerupator.deschis(s, ACUM)
    s = intrerupator.dupa_esec(s, ACUM, prag=3, pauza_sec=120)
    assert intrerupator.deschis(s, ACUM) and s.intrerupt_pana_la == ACUM + dt.timedelta(seconds=120)
    assert intrerupator.deschis(s, ACUM + dt.timedelta(seconds=119))
    assert not intrerupator.deschis(
        s, ACUM + dt.timedelta(seconds=120)
    )  # după pauză: urmează o cerere de probă
    assert intrerupator.dupa_succes(s) == StareSanatate()


def test_proba_esuata_dupa_pauza_redeschide_imediat() -> None:
    dupa_pauza = ACUM + dt.timedelta(seconds=121)
    s = StareSanatate(3, ACUM + dt.timedelta(seconds=120))
    s = intrerupator.dupa_esec(s, dupa_pauza, prag=3, pauza_sec=120)
    assert s.erori_consecutive == 4 and intrerupator.deschis(s, dupa_pauza)


def test_pretul_umbra_este_tokenii_inmultiti_cu_pretul_la_un_milion() -> None:
    from decimal import Decimal

    from app.gateway.apel import pret_umbra

    c = cand(pret_umbra_intrare=0.6, pret_umbra_iesire=0.8)
    assert pret_umbra(c, 1_000_000, 1_000_000) == Decimal("1.400000")
    assert pret_umbra(c, 2500, 500) == Decimal("0.001900")
    assert pret_umbra(c, 0, 0) == Decimal("0.000000")
