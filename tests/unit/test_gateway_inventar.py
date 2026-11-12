"""F3.1 — inventarul de pornire este date coerente: marcaje, date de verificare, nume de variabile, fără chei."""

import re

import pytest

from app.gateway import inventar
from app.gateway.inventar import FURNIZORI, MODELE


def test_inventarul_este_coerent() -> None:
    assert inventar.valideaza() == []


def test_furnizorii_din_documentatie_sunt_in_inventar() -> None:
    # docs/02 §2.2: OpenRouter, Groq, Gemini, Cloudflare Workers AI, Claude
    assert {f.cod for f in FURNIZORI} >= {"openrouter", "groq", "gemini", "cloudflare", "anthropic"}
    assert len({f.tip_api for f in FURNIZORI}) >= 3  # trei API-uri diferite (F3.2)


def test_faptele_din_documentatie_au_valorile_si_marcajele_lor() -> None:
    openrouter = next(f for f in FURNIZORI if f.cod == "openrouter")
    assert (openrouter.limite.cereri_minut, openrouter.limite.cereri_zi) == (20, 50)  # [V] docs/02
    groq = next(m for m in MODELE if m.identificator == "llama-3.3-70b-versatile")
    assert (groq.limite.cereri_minut, groq.limite.cereri_zi, groq.limite.tokeni_zi) == (30, 1000, 200_000)
    assert groq.marcaj == "S" and groq.verificat_la is not None
    gemini = next(f for f in FURNIZORI if f.cod == "gemini")
    assert gemini.uz_comercial is False and gemini.marcaj == "V"  # nivelul gratuit nu intră în producție


def test_nicio_presupunere_nu_se_da_drept_verificata() -> None:
    for obiect in (*FURNIZORI, *MODELE):
        if obiect.marcaj == "I":
            assert obiect.verificat_la is None
        else:
            assert obiect.verificat_la is not None


def test_inventarul_nu_contine_chei() -> None:
    text = repr(FURNIZORI) + repr(MODELE)
    assert not re.search(r"sk-[A-Za-z0-9]{10,}|AIza[0-9A-Za-z_-]{20,}|gsk_[A-Za-z0-9]{10,}", text)
    for f in FURNIZORI:
        assert inventar.NUME_VARIABILA.match(f.cheie_env)
        assert not f.parametri.get("cheie")


@pytest.mark.parametrize(
    "nume", ["AMA_MASTER_KEY", "DATABASE_URL", "AMA_CHEIE_", "ama_cheie_x", "AMA_CHEIE_X Y"]
)
def test_numele_de_variabila_in_afara_prefixului_este_respins(nume: str) -> None:
    assert not inventar.NUME_VARIABILA.match(nume)
