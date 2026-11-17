"""F12.1 — nucleul pur al CRM-ului: normalizarea firmei, domeniul, etapele, celulele de export."""

import pytest

from app.crm import registru


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Cafeneaua Zorilor SRL", "cafeneaua zorilor"),
        ("S.C. Cafeneaua Zorilor S.R.L.", "Cafeneaua  Zorilor"),
        ("Brutăria Ștefan", "brutaria stefan srl-d"),
    ],
)
def test_aceeasi_firma_scrisa_diferit_are_aceeasi_forma(a: str, b: str) -> None:
    assert registru.norma_firma(a) == registru.norma_firma(b)


def test_firme_diferite_raman_diferite_iar_un_nume_doar_din_forma_juridica_nu_dispare() -> None:
    assert registru.norma_firma("Cafeneaua Zorilor") != registru.norma_firma("Cafeneaua Apusului")
    assert registru.norma_firma("SA SRL") == "sa srl"


@pytest.mark.parametrize(
    ("url", "asteptat"),
    [
        ("https://www.Zorilor.example/meniu?x=1", "zorilor.example"),
        ("zorilor.example", "zorilor.example"),
        ("", None),
        ("https://facebook.com/cafeneauazorilor", None),  # pagină pe o platformă comună: nu identifică firma
        ("https://www.instagram.com/zorilor", None),
        ("localhost", None),
    ],
)
def test_domeniul_ca_identitate_a_firmei(url: str, asteptat: str | None) -> None:
    assert registru.domeniu(url) == asteptat


def test_etapele_din_17_7_si_tranzitiile() -> None:
    assert registru.ETAPE == ("nou", "calificat", "apel_programat", "oferta_trimisa", "castigat", "pierdut")
    assert set(registru.TRANZITII) == set(registru.ETAPE) == set(registru.ETICHETE_ETAPA)
    assert registru.TRANZITII["castigat"] == () and registru.TRANZITII["pierdut"] == ()
    for etapa, urmatoare in registru.TRANZITII.items():
        assert etapa not in urmatoare and set(urmatoare) <= set(registru.ETAPE)
        if etapa not in registru.INCHISE:
            assert "pierdut" in urmatoare, "orice lead deschis se poate pierde"
    assert "castigat" not in registru.TRANZITII["nou"], "nu se câștigă un lead fără ofertă"


def test_fiecare_sursa_are_temei_si_eticheta_iar_recomandarea_nu_aduce_acord_de_email() -> None:
    assert set(registru.SURSE) == set(registru.ETICHETE_SURSA)
    assert set(registru.SURSE.values()) == set(registru.ETICHETE_TEMEI)
    assert set(registru.SCOP_CONSIMTAMANT) < set(registru.SURSE)
    for sursa in ("recomandare", "inbox", "programare"):
        assert sursa not in registru.SCOP_CONSIMTAMANT
    assert "lista_tinta" not in registru.SURSE, "conturile-țintă nu au contact automat (17.2)"


@pytest.mark.parametrize("periculos", ["=1+1", "+40 700", "-x", "@cmd", "\tx"])
def test_celulele_de_export_nu_pot_fi_formule(periculos: str) -> None:
    assert registru.celula_csv(periculos) == "'" + periculos
    assert registru.celula_csv("Cafeneaua Zorilor") == "Cafeneaua Zorilor"
    assert registru.celula_csv(None) == ""
