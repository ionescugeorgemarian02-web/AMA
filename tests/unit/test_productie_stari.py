"""F2.3 — mașina de stări a livrabilului (7.2), nucleu pur: fiecare pereche de stări, permisă sau nu."""

import itertools

import pytest

from app.productie import stari
from app.productie.stari import Stare

# Tabelul din 7.2 scris A DOUA OARĂ, independent de codul testat: săgețile permise, ca text.
SAGETI = """
planificat > briefat anulat
briefat > in_scriere coada_de_erori anulat
in_scriere > in_validare esec_temporar coada_de_erori anulat
in_validare > validat in_reparatie carantina esec_temporar coada_de_erori anulat
in_reparatie > in_validare esec_temporar coada_de_erori anulat
validat > asteapta_aprobare aprobat expirat coada_de_erori anulat
asteapta_aprobare > aprobat respins expirat anulat
aprobat > in_randare programat coada_de_erori anulat
in_randare > control_media esec_temporar coada_de_erori anulat
control_media > gata in_randare carantina esec_temporar coada_de_erori anulat
gata > programat coada_de_erori anulat
programat > in_publicare coada_de_erori anulat
in_publicare > publicat esec_temporar coada_de_erori
publicat > in_masurare coada_de_erori
in_masurare > inchis coada_de_erori
carantina > in_reparatie in_validare coada_de_erori anulat
esec_temporar > in_scriere in_validare in_reparatie in_randare control_media in_publicare coada_de_erori anulat
coada_de_erori > briefat in_scriere in_validare in_reparatie validat aprobat in_randare control_media gata programat in_publicare publicat in_masurare anulat
expirat > planificat anulat
"""
PERMISE = {
    (Stare(d.strip()), Stare(la))
    for linie in SAGETI.strip().splitlines()
    for d, _, dest in [linie.partition(">")]
    for la in dest.split()
}
TOATE = list(Stare)


def test_sunt_16_stari_normale_si_6_de_exceptie() -> None:
    assert len(stari.NORMALE) == 16 and len(stari.EXCEPTII) == 6
    assert set(stari.NORMALE) | set(stari.EXCEPTII) == set(Stare)
    assert not set(stari.NORMALE) & set(stari.EXCEPTII)
    assert [s.value for s in stari.NORMALE[:4]] == ["planificat", "briefat", "in_scriere", "in_validare"]
    assert set(stari.ETICHETE) == set(Stare), "fiecare stare are etichetă în română"


@pytest.mark.parametrize(("din", "la"), list(itertools.product(TOATE, TOATE)))
def test_fiecare_pereche_este_permisa_sau_nu_exact_ca_in_tabel(din: Stare, la: Stare) -> None:
    asteptat = (din, la) in PERMISE
    assert stari.este_permisa(din, la) is asteptat
    refuz = stari.motiv_refuz(din, la, anterioara=la if din in stari.REVENIRE else None)
    # cu starea de dinainte potrivită, refuzul vine doar din tabel (sau din „deja în starea asta”)
    assert (refuz is None) is asteptat, refuz


def test_tabelul_are_o_intrare_pe_stare_si_nicio_stare_necunoscuta() -> None:
    assert set(stari.TABEL) == set(Stare)
    assert all(set(t) <= set(Stare) for t in stari.TABEL.values())
    assert all(s not in t for s, t in stari.TABEL.items()), "nicio stare nu duce în ea însăși"


def test_starile_finale_sunt_inchis_respins_anulat() -> None:
    assert {Stare.INCHIS, Stare.RESPINS, Stare.ANULAT} == stari.STARI_FINALE


def test_orice_stare_nefinala_poate_ajunge_la_inchis_sau_la_o_stare_finala() -> None:
    def ajunge(start: Stare) -> set[Stare]:
        vazute, de_vazut = set(), [start]
        while de_vazut:
            s = de_vazut.pop()
            if s in vazute:
                continue
            vazute.add(s)
            de_vazut.extend(stari.TABEL[s])
        return vazute

    for s in Stare:
        if s not in stari.STARI_FINALE:
            assert ajunge(s) & stari.STARI_FINALE, f"din {s} nu se mai iese niciodată"
    assert set(stari.NORMALE) <= ajunge(Stare.PLANIFICAT), "toate stările normale se pot atinge"
    assert set(stari.EXCEPTII) <= ajunge(Stare.PLANIFICAT)


def test_drumul_fericit_parcurge_toate_cele_16_stari_normale() -> None:
    drum = [
        *stari.NORMALE[:11],  # planificat … gata
        Stare.PROGRAMAT,
        Stare.IN_PUBLICARE,
        Stare.PUBLICAT,
        Stare.IN_MASURARE,
        Stare.INCHIS,
    ]
    drum = list(dict.fromkeys(drum))
    assert set(drum) == set(stari.NORMALE)
    # ordinea din 7.2: validat → asteapta_aprobare → aprobat → in_randare → control_media → gata
    ordine = [
        Stare.PLANIFICAT,
        Stare.BRIEFAT,
        Stare.IN_SCRIERE,
        Stare.IN_VALIDARE,
        Stare.VALIDAT,
        Stare.ASTEAPTA_APROBARE,
        Stare.APROBAT,
        Stare.IN_RANDARE,
        Stare.CONTROL_MEDIA,
        Stare.GATA,
        Stare.PROGRAMAT,
        Stare.IN_PUBLICARE,
        Stare.PUBLICAT,
        Stare.IN_MASURARE,
        Stare.INCHIS,
    ]
    for a, b in itertools.pairwise(ordine):
        assert stari.este_permisa(a, b), (a, b)


def test_publicarea_in_curs_nu_se_anuleaza() -> None:
    assert not stari.este_permisa(Stare.IN_PUBLICARE, Stare.ANULAT)
    assert not stari.este_permisa(Stare.PUBLICAT, Stare.ANULAT)


def test_expirat_se_reprogrameaza_dar_nu_se_publica() -> None:
    assert stari.este_permisa(Stare.EXPIRAT, Stare.PLANIFICAT)
    assert not stari.este_permisa(Stare.EXPIRAT, Stare.APROBAT)
    assert not stari.este_permisa(Stare.ASTEAPTA_APROBARE, Stare.PROGRAMAT)
    assert not stari.este_permisa(Stare.ASTEAPTA_APROBARE, Stare.IN_PUBLICARE)


def test_din_esec_temporar_si_coada_de_erori_se_revine_doar_unde_era() -> None:
    # tabelul permite mai multe destinații; regula de revenire le reduce la starea de dinainte
    assert stari.motiv_refuz(Stare.ESEC_TEMPORAR, Stare.IN_VALIDARE, Stare.IN_VALIDARE) is None
    assert "revine doar" in (
        stari.motiv_refuz(Stare.ESEC_TEMPORAR, Stare.IN_SCRIERE, Stare.IN_VALIDARE) or ""
    )
    assert stari.motiv_refuz(Stare.COADA_DE_ERORI, Stare.GATA, Stare.GATA) is None
    assert stari.motiv_refuz(Stare.COADA_DE_ERORI, Stare.GATA, Stare.PROGRAMAT) is not None
    assert stari.motiv_refuz(Stare.COADA_DE_ERORI, Stare.GATA, None) is not None
    # anularea și escaladarea sunt mereu posibile
    assert stari.motiv_refuz(Stare.ESEC_TEMPORAR, Stare.ANULAT, Stare.IN_VALIDARE) is None
    assert stari.motiv_refuz(Stare.ESEC_TEMPORAR, Stare.COADA_DE_ERORI, Stare.IN_VALIDARE) is None
    assert stari.motiv_refuz(Stare.COADA_DE_ERORI, Stare.ANULAT, Stare.IN_VALIDARE) is None


def test_perechile_pentru_baza_sunt_stabile_si_complete() -> None:
    p = stari.perechi()
    assert p == sorted(p) and len(p) == len(set(p)) == len(PERMISE)
    assert set(p) == {(d.value, la.value) for d, la in PERMISE}


def test_motivul_refuzului_este_in_romana_si_nu_contine_date() -> None:
    m = stari.motiv_refuz(Stare.PLANIFICAT, Stare.PUBLICAT)
    assert m == "din „Planificat” nu se poate trece în „Publicat”"
    assert stari.motiv_refuz(Stare.GATA, Stare.GATA) == "livrabilul este deja în starea „Gata”"
