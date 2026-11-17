"""F13.8 — verificarea reclamelor: politici, dezvăluirea AI, urmărirea, potrivirea cu pagina."""

import pytest

from app.reclame import verificare

LINK = "https://agentie.example/audit?utm_source=meta&utm_medium=cpc&utm_campaign=audit"


@pytest.fixture(autouse=True)
def _pagina(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verificare, "CITESTE_PAGINA", lambda url: "Audit gratuit de marketing pentru firme.")


def coduri(titlu: str, text: str, link: str = LINK, **kw: bool) -> set[str]:
    return {p["cod"] for p in verificare.verifica(titlu, text, link, "meta", generat_ai=kw.get("ai", False))}


def test_reclama_curata_trece() -> None:
    assert coduri("Audit gratuit de marketing", "Află unde pierzi clienți, în 48 de ore.") == set()


@pytest.mark.parametrize(
    ("text", "cod"),
    [
        ("Ești supraponderal? Te ajutăm.", "reclame.reclame-atribute-personale"),
        ("Vânzări garantate în 30 de zile.", "reclame.reclame-promisiuni-rezultat"),
        ("Credit rapid pentru firma ta.", "reclame.reclame-categorii-speciale"),
        ("Țigări electronice la reducere.", "reclame.reclame-produse-restrictionate"),
    ],
)
def test_problemele_de_politica_blocheaza(text: str, cod: str) -> None:
    assert cod in coduri("Audit gratuit de marketing", text)


def test_ai_urmarire_si_pagina() -> None:
    assert "dezvaluire_ai" in coduri("Audit gratuit", "Imagine creată pentru tine.", ai=True)
    assert "dezvaluire_ai" not in coduri("Audit gratuit", "Imagine generată cu AI.", ai=True)
    assert "urmarire" in coduri("Audit gratuit", "Text.", link="https://agentie.example/audit")
    assert "potrivire" in coduri("Pantofi sport ieftini", "Reduceri mari.")
