"""F4.7 — bugetul de tokeni al pachetului de context: estimator, priorități, trunchiere deterministă. Nucleu pur."""

from app.creier.buget import Candidat, alege, estimeaza_tokeni

P = ["reguli", "fapte", "oferte", "ghid", "pasaje"]
OBL = frozenset({"reguli"})


def c(sectiune: str, cheie: str, n: int) -> Candidat:
    return Candidat(sectiune, cheie, "x" * n)


def test_estimatorul_este_trei_caractere_pe_token_rotunjit_in_sus() -> None:
    assert estimeaza_tokeni("") == 0 and estimeaza_tokeni("a") == 1 and estimeaza_tokeni("abc") == 1
    assert estimeaza_tokeni("abcd") == 2 and estimeaza_tokeni("x" * 300) == 100


def test_tot_ce_incape_se_pastreaza_in_ordinea_prioritatii() -> None:
    a = alege(
        [c("pasaje", "p", 30), c("fapte", "f", 30), c("reguli", "r", 30)],
        prioritati=P,
        obligatorii=OBL,
        buget=100,
    )
    assert (
        [x.cheie for x in a.pastrate] == ["r", "f", "p"] and a.tokeni == 30 and not a.taiate and not a.depasit
    )


def test_cand_nu_incape_se_pierd_intai_sectiunile_cu_prioritate_mica() -> None:
    cand = [
        c("reguli", "r", 30),
        c("fapte", "f1", 30),
        c("fapte", "f2", 30),
        c("oferte", "o", 30),
        c("pasaje", "p", 30),
    ]
    a = alege(
        cand, prioritati=P, obligatorii=OBL, buget=30
    )  # 10 tokeni per element, 30 de tokeni = 3 elemente
    assert [x.cheie for x in a.pastrate] == ["r", "f1", "f2"]
    assert [(x.cheie, m) for x, m in a.taiate] == [("o", "buget"), ("p", "buget")]
    assert a.tokeni == 30 and a.pe_sectiune == {"reguli": 10, "fapte": 20}


def test_un_element_mare_care_nu_incape_nu_il_blocheaza_pe_cele_mici_de_dupa_el() -> None:
    a = alege([c("fapte", "mare", 300), c("fapte", "mic", 9)], prioritati=P, obligatorii=OBL, buget=10)
    assert [x.cheie for x in a.pastrate] == ["mic"] and [x.cheie for x, _ in a.taiate] == ["mare"]


def test_regulile_intra_mereu_chiar_peste_buget_si_pachetul_spune_ca_a_depasit() -> None:
    a = alege(
        [c("reguli", "r1", 90), c("reguli", "r2", 90), c("fapte", "f", 3)],
        prioritati=P,
        obligatorii=OBL,
        buget=40,
    )
    assert [x.cheie for x in a.pastrate] == ["r1", "r2"] and a.depasit and a.tokeni == 60
    assert [x.cheie for x, _ in a.taiate] == ["f"]


def test_obligatoriile_se_rezerva_primele_chiar_daca_nu_sunt_prima_prioritate() -> None:
    cand = [c("fapte", "f", 30), c("reguli", "r", 60)]
    a = alege(
        cand, prioritati=["fapte", "reguli"], obligatorii=OBL, buget=20
    )  # fapte are prioritate, dar regulile au loc
    assert [x.cheie for x in a.pastrate] == ["r"] and [x.cheie for x, _ in a.taiate] == ["f"]
    assert a.tokeni == 20 and not a.depasit
    b = alege(cand, prioritati=["fapte", "reguli"], obligatorii=OBL, buget=50)
    assert [x.cheie for x in b.pastrate] == ["f", "r"] and b.tokeni == 30 and not b.taiate


def test_determinist_si_independent_de_ordinea_elementelor_din_alte_sectiuni() -> None:
    cand = [
        c("pasaje", "p1", 30),
        c("fapte", "f1", 30),
        c("oferte", "o1", 30),
        c("fapte", "f2", 30),
        c("reguli", "r", 30),
    ]
    a1 = alege(cand, prioritati=P, obligatorii=OBL, buget=45)
    a2 = alege(list(cand), prioritati=P, obligatorii=OBL, buget=45)
    assert a1 == a2
    # 10 tokeni per element, 45 de tokeni: regula, apoi cele două fapte (ordinea dată), apoi nu mai încape nimic întreg
    assert [x.cheie for x in a1.pastrate] == ["r", "f1", "f2", "o1"] and a1.tokeni == 40
    assert [x.cheie for x, _ in a1.taiate] == ["p1"]


def test_un_buget_zero_taie_tot_ce_nu_e_obligatoriu() -> None:
    a = alege([c("fapte", "f", 3), c("reguli", "r", 3)], prioritati=P, obligatorii=OBL, buget=0)
    assert [x.cheie for x in a.pastrate] == ["r"] and a.depasit and a.tokeni == 1
