"""F4.2 — robots.txt (RFC 9309) și utilitarele de adrese. Nucleu pur."""

from app.cercetare import robots as rb
from app.cercetare.url_utile import (
    acelasi_domeniu,
    domeniu_inregistrat,
    este_pagina_probabila,
    normalizeaza,
    rezolva_link,
    suspect_de_capcana,
)

AGENT = "AMA-Colector/0.1 (+https://exemplu.test/bot)"


def test_grupul_specific_agentului_bate_grupul_general() -> None:
    r = rb.parseaza(
        "User-agent: *\nDisallow: /privat/\n\nUser-agent: AMA-Colector\nDisallow: /intern/\nCrawl-delay: 3\n"
    )
    assert r.permite(AGENT, "/privat/x") is True  # grupul nostru nu interzice /privat/
    assert r.permite(AGENT, "/intern/x") is False
    assert r.crawl_delay(AGENT) == 3.0
    assert r.permite("AltBot/1.0", "/privat/x") is False and r.permite("AltBot/1.0", "/intern/x") is True


def test_cea_mai_lunga_regula_castiga_iar_la_egalitate_allow() -> None:
    r = rb.parseaza("User-agent: *\nDisallow: /a\nAllow: /a/b\nDisallow: /a/b/c\nAllow: /x\nDisallow: /x\n")
    assert r.permite(AGENT, "/a/zzz") is False
    assert r.permite(AGENT, "/a/b/zzz") is True
    assert r.permite(AGENT, "/a/b/c/d") is False
    assert r.permite(AGENT, "/x") is True  # egalitate: Allow


def test_metacaracterele_stea_si_dolar() -> None:
    r = rb.parseaza("User-agent: *\nDisallow: /*.pdf$\nDisallow: /cos/*/plata\nDisallow: /*?sesiune=\n")
    assert r.permite(AGENT, "/acte/oferta.pdf") is False
    assert r.permite(AGENT, "/acte/oferta.pdf.html") is True  # `$` ancorează sfârșitul
    assert r.permite(AGENT, "/cos/123/plata") is False and r.permite(AGENT, "/cos/123/livrare") is True
    assert r.permite(AGENT, "/produs?sesiune=abc") is False and r.permite(AGENT, "/produs?pagina=2") is True


def test_disallow_gol_permite_tot_iar_comentariile_si_majusculele_nu_conteaza() -> None:
    r = rb.parseaza("USER-AGENT: *   # toți\nDISALLOW:\n# comentariu\n")
    assert r.permite(AGENT, "/orice") is True
    r2 = rb.parseaza("User-agent: *\nDisallow: /   # tot\n")
    assert r2.permite(AGENT, "/") is False and r2.permite(AGENT, "/a") is False


def test_mai_multe_linii_user_agent_formeaza_un_singur_grup_iar_grupurile_identice_se_unesc() -> None:
    r = rb.parseaza(
        "User-agent: ama-colector\nUser-agent: altbot\nDisallow: /a/\n\nUser-agent: ama-colector\nDisallow: /b/\n"
    )
    assert (
        r.permite(AGENT, "/a/x") is False
        and r.permite(AGENT, "/b/x") is False
        and r.permite(AGENT, "/c") is True
    )


def test_sitemapurile_si_crawl_delay_cu_plafon() -> None:
    r = rb.parseaza(
        "Sitemap: https://exemplu.test/sitemap.xml\nUser-agent: *\nCrawl-delay: 9999\nSitemap: https://exemplu.test/s2.xml\n"
    )
    assert r.sitemapuri == ("https://exemplu.test/sitemap.xml", "https://exemplu.test/s2.xml")
    assert r.crawl_delay(AGENT) == rb.CRAWL_DELAY_MAXIM_SEC
    assert rb.parseaza("User-agent: *\nCrawl-delay: abc\n").crawl_delay(AGENT) is None


def test_starea_cererii_hotaraste_ce_se_intampla_fara_fisier() -> None:
    assert rb.din_status(404).permite(AGENT, "/orice") is True
    assert rb.din_status(410).permite(AGENT, "/orice") is True
    for cod in (401, 403, 429, 500, 503, None):  # prudență: nimic permis
        assert rb.din_status(cod).permite(AGENT, "/") is False
    assert rb.din_status(200, "User-agent: *\nDisallow: /p/").permite(AGENT, "/p/a") is False


def test_fisierul_robots_foarte_mare_se_taie() -> None:
    mare = "User-agent: *\n" + "Disallow: /x\n" * 200_000 + "Disallow: /final\n"
    assert rb.parseaza(mare).permite(AGENT, "/final") is True  # dincolo de limită nu se mai citește


def test_normalizarea_adreselor() -> None:
    assert (
        normalizeaza("HTTP://Brand.Exemplu.test:80/a//b/?utm_source=x&b=2&a=1#sus")
        == "http://brand.exemplu.test/a/b/?a=1&b=2"
    )
    assert normalizeaza("https://brand.exemplu.test:443") == "https://brand.exemplu.test/"
    assert normalizeaza("https://brand.exemplu.test:8443/x") == "https://brand.exemplu.test:8443/x"
    assert normalizeaza("https://brand.exemplu.test/?fbclid=1&gclid=2") == "https://brand.exemplu.test/"


def test_linkuri_care_nu_sunt_pagini_web() -> None:
    for h in ("mailto:a@b.ro", "tel:+40123", "javascript:void(0)", "#sus", "", "  ", "whatsapp://send"):
        assert rezolva_link("https://x.ro/", h) is None
    assert rezolva_link("https://x.ro/a/b", "../c") == "https://x.ro/c"
    assert rezolva_link("https://x.ro/a", "//cdn.y.ro/z") == "https://cdn.y.ro/z"
    assert not este_pagina_probabila("https://x.ro/poza.JPG") and este_pagina_probabila("https://x.ro/despre")


def test_domeniul_inregistrat() -> None:
    assert domeniu_inregistrat("blog.brand.ro") == "brand.ro"
    assert domeniu_inregistrat("www.brand.com.ro") == "brand.com.ro"
    assert domeniu_inregistrat("brand.ro") == "brand.ro"
    assert domeniu_inregistrat("127.0.0.1") == "127.0.0.1" and domeniu_inregistrat("localhost") == "localhost"
    assert acelasi_domeniu("shop.brand.ro", "www.brand.ro") and not acelasi_domeniu(
        "brand.ro", "brand.ro.evil.test"
    )
    assert not acelasi_domeniu("alta.com.ro", "brand.com.ro")


def test_euristici_contra_capcanelor_de_linkuri() -> None:
    assert suspect_de_capcana("https://x.ro/a/a/a/a")
    assert suspect_de_capcana("https://x.ro/" + "/".join(f"s{i}" for i in range(20)))
    assert suspect_de_capcana("https://x.ro/?" + "&".join(f"p{i}=1" for i in range(9)))
    assert not suspect_de_capcana("https://x.ro/produse/cafea/arabica?pagina=2")
