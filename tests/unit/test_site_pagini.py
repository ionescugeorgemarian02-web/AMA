"""F7.1 — paginile site-ului ca date: toate cele din 19.1 există, cu titlu și descriere potrivite pentru căutare."""

from app.site import blog, pagini
from app.site.web import _inapoi_sigur

CERUTE = {"", "audit", "servicii", "preturi", "cum-lucram", "studii-de-caz", "blog", "despre", "transparenta-ai",
          "legal", "stare", "legal/termeni", "legal/confidentialitate", "legal/cookie-uri", "legal/acord-prelucrare",
          "legal/stergere-date"}  # fmt: skip


def test_toate_paginile_din_19_1_exista_cu_titlu_si_descriere() -> None:
    assert set(pagini.TOATE) == CERUTE
    for p in pagini.TOATE.values():
        assert 3 <= len(p.titlu) <= 70 and 30 <= len(p.descriere) <= 160, p.cale
    assert set(pagini.CAI_SITEMAP) == CERUTE


def test_preturile_vin_din_planuri() -> None:
    text = " ".join(s.titlu for s in pagini.TOATE["preturi"].sectiuni)
    assert "1.490 lei / lună" in text and "Creștere" in text


def test_slug_fara_diacritice_si_inapoi_sigur() -> None:
    assert blog.slug_din("Cum alegi cafeaua? Ghid pentru Brașov!") == "cum-alegi-cafeaua-ghid-pentru-brasov"
    assert _inapoi_sigur("/site/preturi") == "/site/preturi"
    for rau in ("https://rau.example/site", "//rau.example", "/panou", "/site//x"):
        assert _inapoi_sigur(rau) == "/site"
