"""F7.1 — site-ul public. „Gata când”: toate paginile sunt publice și rapide pe telefon. Rapid = randat pe server,
fără niciun script executabil, HTML mic, o foaie de stil mică; plus acordul pentru cookie-uri (fără analiză înainte
de acord), adresele canonice, datele structurate și harta site-ului."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import sesiune_agentie
from app.site import analiza, blog, pagini
from tests.integration.conftest import csrf_din

pytestmark = pytest.mark.db
CSS = Path(__file__).resolve().parents[2] / "app" / "web" / "static" / "css" / "site.css"


def cale(c: str) -> str:
    return "/site" + ("/" + c if c else "")


def test_toate_paginile_sunt_publice_si_usoare_pe_telefon(client: TestClient) -> None:
    for c in pagini.TOATE:
        r = client.get(cale(c))
        assert r.status_code == 200, c
        h = r.text
        assert len(r.content) < 20_000, (c, len(r.content))
        assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in h
        assert f'<link rel="canonical" href="http://localhost:8000/site{"/" + c if c else "/"}">' in h
        assert "<script src" not in h and re.findall(r"<script(?![^>]*application/ld\+json)", h) == []
        ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)
        assert ld is not None and json.loads(ld.group(1))["@type"] == "Organization"
        assert "Content-Security-Policy" in r.headers
        if c not in ("audit", "stare"):
            assert h.count('class="cta" href="/site/audit"') == 1, c
    assert CSS.stat().st_size < 6_000
    assert client.get("/site/nu-exista").status_code == 404


def test_fara_analiza_inainte_de_acord_apoi_numarare_anonima(client: TestClient) -> None:
    inainte = analiza.vizite().get("/preturi", 0)
    h = client.get("/site/preturi").text
    assert 'action="/site/consimtamant"' in h and "Accept analiza" in h
    assert analiza.vizite().get("/preturi", 0) == inainte  # fără acord nu se scrie nimic
    assert not client.cookies.get(analiza.COOKIE)
    assert client.post("/site/consimtamant", data={"alege": "analiza"}).status_code == 403  # fără CSRF
    r = client.post("/site/consimtamant", data={"alege": "analiza", "inapoi": "/site/preturi", "csrf_token": csrf_din(h)},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"] == "/site/preturi"
    assert "httponly" in r.headers["set-cookie"].lower()
    h = client.get("/site/preturi").text
    assert "Accept analiza" not in h
    assert analiza.vizite().get("/preturi", 0) == inainte + 1
    # retragerea acordului din pagina Cookie-uri
    assert "analiză acceptată" in client.get("/site/legal/cookie-uri").text and "Accept analiza" not in h
    h = client.get("/site/legal/cookie-uri").text
    client.post(
        "/site/consimtamant",
        data={"alege": "esential", "inapoi": "/site/legal/cookie-uri", "csrf_token": csrf_din(h)},
    )
    client.get("/site/preturi")
    assert analiza.vizite().get("/preturi", 0) == inainte + 1
    j = csrf_din(h)
    r = client.post("/site/consimtamant", data={"alege": "analiza", "inapoi": "https://rau.example/", "csrf_token": j},
                    follow_redirects=False)  # fmt: skip
    assert r.headers["location"] == "/site"
    assert client.post("/site/consimtamant", data={"alege": "tot", "csrf_token": j}).status_code == 422


def test_blogul_harta_site_ului_si_robots(client: TestClient) -> None:
    with sesiune_agentie() as db:
        blog.publica(
            db, titlu="Cum alege o cafenea mică un canal", descriere="Un articol de probă pentru harta site-ului.",
            corp=[{"titlu": "Pe scurt", "paragrafe": ["Primul paragraf."]}],
            surse=[{"titlu": "Sursa de probă", "url": "https://example.org/sursa"}],
        )  # fmt: skip
    h = client.get("/site/blog").text
    assert 'href="/site/blog/cum-alege-o-cafenea-mica-un-canal"' in h
    a = client.get("/site/blog/cum-alege-o-cafenea-mica-un-canal")
    assert a.status_code == 200 and '"@type": "BlogPosting"' in a.text and "Sursa de probă" in a.text
    assert "Conținut creat cu ajutorul AI" in a.text
    assert client.get("/site/blog/NU_e_slug").status_code == 404
    x = client.get("/site/sitemap.xml")
    assert x.headers["content-type"].startswith("application/xml")
    for c in pagini.TOATE:
        assert f"<loc>http://localhost:8000/site{'/' + c if c else '/'}</loc>" in x.text
    assert "/site/blog/cum-alege-o-cafenea-mica-un-canal</loc>" in x.text
    assert "Sitemap: http://localhost:8000/site/sitemap.xml" in client.get("/site/robots.txt").text
    assert "funcționează normal" in client.get("/site/stare").text
