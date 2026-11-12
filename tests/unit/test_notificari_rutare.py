"""F1.7 — nivelurile de notificare (18.6) și rutarea pe canale: funcție pură, fără bază de date."""

import json

import pytest

from app.operare import notificari
from app.operare.alerte import format_mesaj
from app.operare.notificari import Canal, Nivel, Notificare


def test_critic_merge_pe_push_si_telegram() -> None:
    assert notificari.canale_pentru(Nivel.CRITIC) == {Canal.PUSH, Canal.TELEGRAM}


def test_important_merge_doar_pe_push() -> None:
    assert notificari.canale_pentru(Nivel.IMPORTANT) == {Canal.PUSH}


def test_informativ_merge_in_rezumatul_zilnic_nu_pe_push() -> None:
    assert notificari.canale_pentru(Nivel.INFORMATIV) == {Canal.REZUMAT_ZILNIC}


@pytest.mark.parametrize("nivel", list(Nivel))
def test_fiecare_nivel_are_rutare(nivel: Nivel) -> None:
    assert notificari.canale_pentru(nivel)


def test_payload_are_forma_asteptata_si_pastreaza_diacriticele() -> None:
    p = json.loads(
        Notificare(nivel=Nivel.CRITIC, titlu="Cheltuială anormală", text="Verifică", url="/alerte").payload()
    )
    assert p == {"titlu": "Cheltuială anormală", "text": "Verifică", "url": "/alerte", "nivel": "critic"}


@pytest.mark.parametrize("url", ["https://rau.example/x", "//rau.example", "javascript:alert(1)", "alerte"])
def test_payload_nu_accepta_adrese_in_afara_aplicatiei(url: str) -> None:
    p = json.loads(Notificare(nivel=Nivel.IMPORTANT, titlu="t", text="x", url=url).payload())
    assert p["url"] == "/"


def test_mesajul_de_alerta_are_nivelul_si_titlul() -> None:
    assert (
        format_mesaj("critic", "Sistem oprit", "Baza nu răspunde")
        == "[CRITIC] Sistem oprit\nBaza nu răspunde"
    )
