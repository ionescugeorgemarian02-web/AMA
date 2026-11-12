"""F2.10 — nivelurile de autonomie (7.4), nucleu pur: matricea, eșantionul determinist, canalele cu consimțământ."""

import itertools
import uuid

import pytest

from app.ids import new_id
from app.productie.reguli_autonomie import (
    CANALE_CONSIMTAMANT_IMPLICITE,
    ETICHETE_CLASA,
    ETICHETE_NIVEL,
    NIVEL_IMPLICIT,
    REGIM,
    Clasa,
    Decizie,
    Nivel,
    cere_aprobare,
    esantionat,
    nivel_efectiv,
    retrogradat,
)

C, N = Clasa, Nivel
U, AP, AU = Decizie.UMBRA, Decizie.APROBARE, Decizie.AUTOMAT
LIVRABIL = uuid.UUID("01a1ceb0-0000-7000-8000-000000000001")


def cu_rata(rata: float, **kw: object) -> dict[str, object]:
    return {"rata_l2": rata, "rata_l3": rata, **kw}


# Matricea din 7.4 scrisă a doua oară, independent de cod: ce se întâmplă la L0 … L4, FĂRĂ eșantion
# (rata 0: nimeni nu e ales) și CU eșantion total (rata 1: toți sunt aleși).
FARA_ESANTION = {
    C.PUBLICARE_CONTINUT: (U, AP, AU, AU, AU),
    C.RASPUNS_INBOX: (U, AP, AP, AU, AU),
    C.SCHIMBARE_RECLAME: (U, AP, AP, AU, AU),
    C.SCHIMBARE_STRATEGIE: (U, AP, AP, AP, AU),
    C.CHELTUIALA: (U, AP, AP, AU, AU),
}
CU_ESANTION_TOTAL = {
    C.PUBLICARE_CONTINUT: (U, AP, AP, AP, AP),
    C.RASPUNS_INBOX: (U, AP, AP, AP, AP),
    C.SCHIMBARE_RECLAME: (U, AP, AP, AP, AP),
    C.SCHIMBARE_STRATEGIE: (U, AP, AP, AP, AU),  # la L4 strategia e în perimetru, fără eșantion
    C.CHELTUIALA: (U, AP, AP, AP, AP),
}


@pytest.mark.parametrize(("clasa", "nivel"), list(itertools.product(Clasa, Nivel)))
def test_matricea_clasa_x_nivel_exhaustiv(clasa: Clasa, nivel: Nivel) -> None:
    assert cere_aprobare(nivel, clasa, LIVRABIL, **cu_rata(0.0)) is FARA_ESANTION[clasa][nivel]  # type: ignore[arg-type]
    assert cere_aprobare(nivel, clasa, LIVRABIL, **cu_rata(1.0)) is CU_ESANTION_TOTAL[clasa][nivel]  # type: ignore[arg-type]


def test_matricea_din_cod_are_cinci_clase_si_cinci_niveluri() -> None:
    assert set(REGIM) == set(Clasa) and len(Clasa) == 5
    assert all(len(r) == 5 for r in REGIM.values()) and len(Nivel) == 5
    assert set(ETICHETE_CLASA) == set(Clasa) and set(ETICHETE_NIVEL) == set(Nivel)
    assert NIVEL_IMPLICIT is Nivel.L1


def test_implicit_este_l1_adica_totul_la_aprobare() -> None:
    for clasa in Clasa:
        assert cere_aprobare(NIVEL_IMPLICIT, clasa, new_id()) is Decizie.APROBARE


def test_l0_produce_dar_nu_publica_si_nu_cere_nimic() -> None:
    for clasa in Clasa:
        d = cere_aprobare(N.L0, clasa, LIVRABIL)
        assert d is Decizie.UMBRA and not d.cere_aprobare


def test_decizia_este_deterministă_pentru_acelasi_livrabil() -> None:
    ids = [new_id() for _ in range(200)]
    prima = [cere_aprobare(N.L2, C.PUBLICARE_CONTINUT, i) for i in ids]
    for _ in range(3):
        assert [cere_aprobare(N.L2, C.PUBLICARE_CONTINUT, i) for i in ids] == prima
    assert esantionat(ids[0], C.PUBLICARE_CONTINUT, 0.5) == esantionat(ids[0], C.PUBLICARE_CONTINUT, 0.5)


def test_un_id_fix_are_un_raspuns_fix_reproductibil() -> None:
    """Valori ancorate: dacă funcția de eșantionare s-ar schimba, livrabilele vechi și-ar schimba soarta.
    Pentru acest id și clasa „publicare de conținut”, SHA-256 dă poziția 0,4925; pentru „răspuns în inbox”, 0,5806."""
    fix = uuid.UUID("01a1ceb0-1111-7222-8333-444444444444")
    raspunsuri = {
        r: esantionat(fix, C.PUBLICARE_CONTINUT, r) for r in (0.0, 0.05, 0.15, 0.49, 0.50, 0.95, 1.0)
    }
    assert raspunsuri == {0.0: False, 0.05: False, 0.15: False, 0.49: False, 0.5: True, 0.95: True, 1.0: True}
    assert esantionat(fix, C.RASPUNS_INBOX, 0.55) is False and esantionat(fix, C.RASPUNS_INBOX, 0.59) is True


@pytest.mark.parametrize(("nivel", "rata"), [(N.L2, 0.15), (N.L3, 0.075)])
def test_ponderea_eșantionului_este_cea_configurata(nivel: Nivel, rata: float) -> None:
    n = 20_000
    kw = {"rata_l2": 0.15, "rata_l3": 0.075}
    la_om = sum(
        cere_aprobare(nivel, C.PUBLICARE_CONTINUT, new_id(), **kw) is Decizie.APROBARE  # type: ignore[arg-type]
        for _ in range(n)
    )
    assert abs(la_om / n - rata) < 0.01, f"{la_om / n:.4f} față de {rata}"


def test_intervalele_din_7_4_sunt_implicite() -> None:
    from app.productie.reguli_autonomie import RATA_L2_IMPLICITA, RATA_L3_IMPLICITA

    assert 0.10 <= RATA_L2_IMPLICITA <= 0.20 and 0.05 <= RATA_L3_IMPLICITA <= 0.10


def test_eșantionul_depinde_de_clasa_si_de_livrabil() -> None:
    ids = [new_id() for _ in range(300)]
    a = [esantionat(i, C.PUBLICARE_CONTINUT, 0.5) for i in ids]
    b = [esantionat(i, C.RASPUNS_INBOX, 0.5) for i in ids]
    assert a != b, "clase diferite nu aleg aceleași livrabile"
    assert 0.35 < sum(a) / len(a) < 0.65


def test_rata_invalida_este_refuzata() -> None:
    for rata in (-0.1, 1.1):
        with pytest.raises(ValueError):
            esantionat(LIVRABIL, C.PUBLICARE_CONTINUT, rata)


def test_ce_nu_trece_verificarile_merge_la_om_chiar_la_nivel_inalt() -> None:
    for nivel in (N.L2, N.L3, N.L4):
        assert (
            cere_aprobare(nivel, C.PUBLICARE_CONTINUT, LIVRABIL, verificari_ok=False, **cu_rata(0.0))  # type: ignore[arg-type]
            is Decizie.APROBARE
        )
    assert cere_aprobare(N.L0, C.PUBLICARE_CONTINUT, LIVRABIL, verificari_ok=False) is Decizie.UMBRA


def test_peste_plafon_sau_in_afara_perimetrului_merge_la_om() -> None:
    assert cere_aprobare(N.L3, C.CHELTUIALA, LIVRABIL, in_limite=False, **cu_rata(0.0)) is Decizie.APROBARE  # type: ignore[arg-type]
    assert cere_aprobare(N.L3, C.CHELTUIALA, LIVRABIL, in_limite=True, **cu_rata(0.0)) is Decizie.AUTOMAT  # type: ignore[arg-type]
    assert cere_aprobare(N.L4, C.SCHIMBARE_STRATEGIE, LIVRABIL, in_limite=False) is Decizie.APROBARE
    assert cere_aprobare(N.L4, C.SCHIMBARE_STRATEGIE, LIVRABIL, in_limite=True) is Decizie.AUTOMAT


@pytest.mark.parametrize("nivel", [N.L2, N.L3, N.L4])
def test_canalele_cu_consimtamant_per_postare_raman_la_l1(nivel: Nivel) -> None:
    assert "tiktok" in CANALE_CONSIMTAMANT_IMPLICITE
    for clasa in Clasa:
        assert cere_aprobare(nivel, clasa, LIVRABIL, canal="tiktok", **cu_rata(0.0)) is Decizie.APROBARE  # type: ignore[arg-type]
    assert (
        cere_aprobare(nivel, C.PUBLICARE_CONTINUT, LIVRABIL, canal="TikTok", **cu_rata(0.0))
        is Decizie.APROBARE
    )  # type: ignore[arg-type]
    # alt canal, același nivel: trece singur
    assert (
        cere_aprobare(nivel, C.PUBLICARE_CONTINUT, LIVRABIL, canal="facebook", **cu_rata(0.0))
        is Decizie.AUTOMAT
    )  # type: ignore[arg-type]


def test_canalul_cu_consimtamant_la_l0_ramane_umbra_nu_urca_la_l1() -> None:
    assert nivel_efectiv(N.L0, "tiktok", {"tiktok"}) is N.L0
    assert cere_aprobare(N.L0, C.PUBLICARE_CONTINUT, LIVRABIL, canal="tiktok") is Decizie.UMBRA


def test_lista_canalelor_cu_consimtamant_este_o_configurare() -> None:
    assert nivel_efectiv(N.L3, "instagram", {"tiktok"}) is N.L3
    assert nivel_efectiv(N.L3, "instagram", {"tiktok", "instagram"}) is N.L1
    assert nivel_efectiv(N.L3, None, {"tiktok"}) is N.L3
    d = cere_aprobare(
        N.L3,
        C.PUBLICARE_CONTINUT,
        LIVRABIL,
        canal="instagram",
        canale_consimtamant={"instagram"},
        **cu_rata(0.0),  # type: ignore[arg-type]
    )
    assert d is Decizie.APROBARE


def test_retrogradarea_coboara_un_nivel_cu_podeaua_l0() -> None:
    assert [retrogradat(n) for n in Nivel] == [N.L0, N.L0, N.L1, N.L2, N.L3]
