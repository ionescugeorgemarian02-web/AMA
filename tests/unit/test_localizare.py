"""F16.3 — a doua limbă (engleza): catalogul interfeței, alegerea limbii, regulile de validare pe limbă, editorul."""

import datetime as dt
import re
import uuid
from pathlib import Path

from starlette.requests import Request

from app import localizare
from app.continut import editor
from app.validare import limba, limba_en, structura
from app.validare.intrare import Continut, Intrare, SituatieLivrabil
from app.validare.verdict import Rezultat

EN = ("Our new chocolate cake is ready for the weekend, and you can order it today from the shop "
      "or online, with delivery in the city.")  # fmt: skip
RO = ("Tortul nostru nou de ciocolată este gata pentru weekend și îl poți comanda azi din cofetărie "
      "sau online, cu livrare în oraș.")  # fmt: skip
SABLOANE = Path(__file__).resolve().parents[2] / "app" / "web" / "templates" / "portal"


def cerere(**antete: str) -> Request:
    h = [(k.lower().replace("_", "-").encode(), v.encode()) for k, v in antete.items()]
    return Request({"type": "http", "headers": h})


def intrare(text: str, **campuri: object) -> Intrare:
    sit = SituatieLivrabil(uuid.uuid4(), uuid.uuid4(), "postare", "facebook", 1, 0)
    return Intrare(sit, Continut(1, text, dict(campuri)), dt.datetime(2026, 11, 18, tzinfo=dt.UTC))


def test_fiecare_text_t_din_portal_are_traducere() -> None:
    texte = set()
    for f in SABLOANE.glob("*.html"):
        texte |= set(re.findall(r"""\bt\(["']([^"']+)["']\)""", f.read_text()))
    texte |= {"Acasă", "Aprobări", "Calendar", "Materiale", "Cont"}  # meniul, trecut prin t(eticheta)
    assert texte and localizare.lipsa(sorted(texte), "en") == []
    assert (
        localizare.traduce("Aprobări", "en") == "Approvals"
        and localizare.traduce("Aprobări", "ro") == "Aprobări"
    )
    assert localizare.traduce("Text necunoscut", "en") == "Text necunoscut"


def test_limba_din_cerere() -> None:
    assert localizare.din_cerere(cerere()) == "ro"
    assert localizare.din_cerere(cerere(accept_language="en-GB,en;q=0.9")) == "en"
    assert localizare.din_cerere(cerere(accept_language="de-DE")) == "ro"
    assert localizare.din_cerere(cerere(accept_language="en", cookie="ama_limba=ro")) == "ro"
    assert localizare.normalizeaza("EN-us") == "en" and localizare.normalizeaza("xx") == "ro"


def test_g1_cere_limba_clientului() -> None:
    assert not [p for p in structura.probleme_structura("postare", "facebook", Continut(1, EN), "en")
                if p.regula == "G1.limba"]  # fmt: skip
    assert [
        p
        for p in structura.probleme_structura("postare", "facebook", Continut(1, RO), "en")
        if p.regula == "G1.limba"
    ]
    assert [
        p
        for p in structura.probleme_structura("postare", "facebook", Continut(1, EN))
        if p.regula == "G1.limba"
    ]
    assert structura.g1(intrare(EN, limba="en")).rezultat is not Rezultat.ESEC


def test_g10_pe_limba_continutului() -> None:
    assert limba.g10_reguli(intrare(EN, limba="en")).rezultat is not Rezultat.ESEC
    amestec = "Our cake is gata și foarte bună, comandă acum din cofetărie today."
    assert "G10.diacritice_in_engleza" in [p.regula for p in limba_en.probleme_limba_en(amestec)]
    assert limba.g10_reguli(intrare(amestec, limba="en")).rezultat is Rezultat.ESEC
    assert limba_en.probleme_limba_en("Visit Cofetăria Zorilor on Strada Lungă.") == [], "numele proprii trec"
    assert [p.regula for p in limba_en.probleme_limba_en("The „best” cake")] == ["G10.ghilimele_en"]
    assert (
        limba_en.limba_intrare(intrare(EN)) == "ro"
        and limba_en.limba_intrare(intrare(EN, limba="en")) == "en"
    )
    assert all(n != "limba" for n, _ in Continut(1, EN, {"limba": "en"}).texte())


def test_editorul_foloseste_ghilimelele_limbii() -> None:
    assert editor.editeaza('Say "hello" today.', "en") == "Say “hello” today."
    assert editor.editeaza('Spune "bună" azi.') == "Spune „bună” azi."


def test_instructiunea_de_continut() -> None:
    assert localizare.instructiune_continut("ro") == ""
    assert "English" in localizare.instructiune_continut("en")
