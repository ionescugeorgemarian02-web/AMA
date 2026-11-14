"""F10.7 — nucleele pure ale cercetătorului de tendințe: potrivirea cu nișa, gruparea, semnalul slab,
excluderea subiectelor sensibile, citirea RSS și YouTube."""

import datetime as dt

from app.cercetare import tendinte as t
from app.cercetare.tendinte import Semnal

ZI = dt.date(2026, 11, 14)
TERMENI = ["cafea", "espresso", "prăjitorie"]
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Pre&#539;ul cafelei cre&#537;te din nou</title><link>https://stiri.exemplu.test/cafea</link>
<pubDate>Fri, 13 Nov 2026 08:00:00 +0000</pubDate></item>
<item><title></title><link>https://stiri.exemplu.test/gol</link></item>
<item><title>Meci decisiv diseara</title></item></channel></rss>"""


def test_potrivirea_ignora_diacriticele_si_numara_termenii() -> None:
    assert t.potrivire("Cea mai bună PRĂJITORIE de cafea", TERMENI) == (0.67, ["cafea", "prăjitorie"])
    assert t.potrivire("cafeaua de dimineață", TERMENI)[1] == ["cafea"], "se potrivește ca rădăcină"
    assert t.potrivire("Prețul cafelei crește", TERMENI)[1] == ["cafea"], "forma flexionată"
    assert t.potrivire("cold brew la doză", ["cold brew"])[1] == ["cold brew"]
    assert t.potrivire("un brew rece", ["cold brew"])[1] == [], "termenul din două cuvinte le cere pe ambele"
    assert t.potrivire("ceaiul de seară", ["ceai", "tei"])[1] == ["ceai"], "termenii scurți doar exact"
    assert t.potrivire("meci de fotbal", TERMENI) == (0.0, [])
    assert t.potrivire("espresso, cafea și o prăjitorie nouă, cafea", TERMENI)[0] == 1.0


def test_doua_surse_confirma_una_singura_e_semnal_slab() -> None:
    semnale = [
        Semnal("Prețul cafelei crește din nou", "google_tendinte", "https://a.exemplu.test/1"),
        Semnal("Crește prețul cafelei", "rss:stiri.exemplu.test", "https://stiri.exemplu.test/2"),
        Semnal("Rețetă de espresso tonic", "youtube", "https://www.youtube.com/watch?v=x"),
        Semnal("Meci decisiv diseară", "google_tendinte"),
    ]
    fise = t.fise_din_semnale(semnale, TERMENI, ZI)
    assert [(f.subiect, f.semnal, f.risc) for f in fise] == [
        ("Prețul cafelei crește din nou", "confirmat", "scazut"),
        ("Rețetă de espresso tonic", "slab", "drepturi"),
    ], "fără potrivire cu nișa nu iese fișă; clipul altcuiva cere atenție la drepturi"
    assert len(fise[0].dovezi) == 2 and fise[0].dovezi[1]["url"].endswith("/2")
    assert "cafea" in fise[0].unghi and fise[0].unghi.startswith("Ciornă:")


def test_subiectele_sensibile_sunt_marcate_si_fara_unghi() -> None:
    [f] = t.fise_din_semnale(
        [Semnal("Accident grav lângă o prăjitorie de cafea", "google_tendinte")], TERMENI, ZI
    )
    assert f.risc == "sensibil" and f.unghi == ""
    assert t.sensibil("Trei victime după incendiu") and not t.sensibil("Mortar de piatră pentru cafea")


def test_rss_se_citeste_iar_documentele_periculoase_sunt_refuzate() -> None:
    s = t.din_rss(RSS, "rss:stiri.exemplu.test")
    assert [x.subiect for x in s] == ["Prețul cafelei crește din nou", "Meci decisiv diseara"]
    assert s[0].url == "https://stiri.exemplu.test/cafea" and s[0].la == dt.date(2026, 11, 13)
    atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Cafea</title><link href="https://x.test/a"/></entry></feed>'
    assert t.din_rss(atom, "rss:x")[0].url == "https://x.test/a"
    bomba = b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]><rss><channel><item><title>&lol;</title></item></channel></rss>'
    assert t.din_rss(bomba, "rss:x") == [] and t.din_rss(b"<rss><neinchis>", "rss:x") == []


def test_youtube_si_titlul_paginii() -> None:
    corp = b'{"items": [{"id": "abc", "snippet": {"title": "Latte art", "publishedAt": "2026-11-12T10:00:00Z"}}, {"id": "", "snippet": {}}]}'
    [s] = t.din_youtube(corp)
    assert (s.sursa, s.url, s.la) == ("youtube", "https://www.youtube.com/watch?v=abc", dt.date(2026, 11, 12))
    assert t.din_youtube(b"nu e json") == []
    pagina = b'<html><head><title>Cold brew &amp; tonic</title><meta property="og:description" content="Re\xc8\x9beta verii"></head></html>'
    assert t.titlu_pagina(pagina) == "Cold brew & tonic · Rețeta verii"
    assert t.titlu_pagina(b"<title><script>x</script>Bun</title>") == "x Bun"
    assert t.urmatoarea_zi_lucratoare(dt.date(2026, 11, 13)) == dt.date(2026, 11, 16), "vineri → luni"
