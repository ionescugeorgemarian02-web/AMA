"""F4.2 — descărcătorul politicos, cu transport fals (fără rețea): SSRF la fiecare redirecționare, robots.txt și
Crawl-delay, limita de octeți aplicată în flux, tipuri de conținut, fără credențiale."""

import gzip
from collections.abc import Callable, Iterator

import httpx
import pytest

from app.cercetare.descarcator import Descarcator, Limite, Sarit

UA = "AMA-Colector/0.1 (bot; +https://exemplu.test/colector)"
PUBLIC = "93.184.216.34"
IP_GAZDE = {
    "brand.exemplu.test": PUBLIC,
    "www.brand.exemplu.test": PUBLIC,
    "intern.brand.exemplu.test": "10.0.0.7",
}
ROBOTS_OK = "User-agent: *\nDisallow: /privat/\n"


class Ceas:
    def __init__(self) -> None:
        self.t = 1000.0
        self.pauze: list[float] = []

    def __call__(self) -> float:
        return self.t

    def dormi(self, s: float) -> None:
        self.pauze.append(s)
        self.t += s


class Site:
    """Transport fals: pagini după (gazdă, cale); înregistrează fiecare cerere."""

    def __init__(
        self, pagini: dict[str, Callable[[httpx.Request], httpx.Response] | tuple[int, dict[str, str], bytes]]
    ):
        self.pagini = pagini
        self.cereri: list[httpx.Request] = []

    def __call__(self, cerere: httpx.Request) -> httpx.Response:
        self.cereri.append(cerere)
        gazda = cerere.headers["host"].split(":")[0]
        cheie = f"{gazda}{cerere.url.path}"
        p = self.pagini.get(cheie)
        if p is None:
            return httpx.Response(404, text="nu exista")
        if callable(p):
            return p(cerere)
        cod, antete, corp = p
        return httpx.Response(cod, headers=antete, content=corp)

    def cai(self) -> list[str]:
        return [f"{c.headers['host']}{c.url.path}" for c in self.cereri]


def html(corp: str = "x" * 80) -> tuple[int, dict[str, str], bytes]:
    return (
        200,
        {"content-type": "text/html; charset=utf-8"},
        f"<html><body><p>{corp}</p></body></html>".encode(),
    )


def robots(text: str = ROBOTS_OK) -> tuple[int, dict[str, str], bytes]:
    return 200, {"content-type": "text/plain"}, text.encode()


def desc(site: Site, ceas: Ceas | None = None, **limite: object) -> Descarcator:
    c = ceas or Ceas()
    limite = {"pauza_sec": 0.0, **limite}
    return Descarcator(
        user_agent=UA, radacina="https://brand.exemplu.test/", limite=Limite(**limite),  # type: ignore[arg-type]
        transport=httpx.MockTransport(site), rezolva=lambda g, p: [IP_GAZDE[g]] if g in IP_GAZDE else ["10.1.1.1"],
        ceas=c, dormi=c.dormi,
    )  # fmt: skip


def refuza(d: Descarcator, url: str) -> Sarit:
    with pytest.raises(Sarit) as exc:
        d.ia_pagina(url)
    return exc.value


def test_conexiunea_merge_la_adresa_verificata_cu_antetul_host_si_user_agent_propriu() -> None:
    site = Site(
        {"brand.exemplu.test/robots.txt": robots(), "brand.exemplu.test/despre": html("text de probă " * 5)}
    )
    d = desc(site)
    r = d.ia_pagina("https://Brand.Exemplu.test/despre#sus")
    assert r.cod == 200 and b"text de" in r.corp and r.url == "https://brand.exemplu.test/despre"
    cerere = site.cereri[-1]
    assert cerere.url.host == PUBLIC  # nu se mai rezolvă a doua oară: conexiune la adresa verificată
    assert cerere.headers["host"] == "brand.exemplu.test" and cerere.headers["user-agent"] == UA
    assert cerere.extensions["sni_hostname"] == "brand.exemplu.test"
    assert "cookie" not in cerere.headers and "authorization" not in cerere.headers


def test_o_destinatie_care_se_rezolva_la_o_adresa_privata_este_refuzata_la_redirectionare() -> None:
    site = Site({
        "brand.exemplu.test/robots.txt": robots(),
        "brand.exemplu.test/spre-intern": (302, {"location": "https://intern.brand.exemplu.test/admin"}, b""),
        "intern.brand.exemplu.test/admin": html("secret intern"),
    })  # fmt: skip
    e = refuza(desc(site), "https://brand.exemplu.test/spre-intern")
    assert e.cod == "adresa_privata"
    assert not any("intern.brand" in c for c in site.cai())  # nicio cerere nu a plecat spre adresa privată


@pytest.mark.parametrize(
    ("destinatie", "coduri"),
    [
        ("http://169.254.169.254/latest/meta-data/", ("redirect_alt_domeniu",)),
        ("http://127.0.0.1:8000/", ("redirect_alt_domeniu", "port_nepermis")),
        ("http://[::1]/", ("redirect_alt_domeniu",)),
        ("ftp://brand.exemplu.test/fisier", ("schema_nepermisa",)),
        ("file:///etc/passwd", ("schema_nepermisa",)),
        ("gopher://brand.exemplu.test/", ("schema_nepermisa",)),
        ("https://utilizator:parola@brand.exemplu.test/", ("url_cu_credentiale",)),  # pragma: allowlist secret
        ("http://brand.exemplu.test:22/", ("port_nepermis",)),
        ("http://alt-domeniu.test/pagina", ("redirect_alt_domeniu",)),
        ("http://brand.exemplu.test.evil.test/", ("redirect_alt_domeniu",)),
    ],
)  # fmt: skip
def test_redirectionarile_periculoase_sau_in_alt_domeniu_sunt_refuzate_fara_nicio_cerere(
    destinatie: str, coduri: tuple[str, ...]
) -> None:
    site = Site({
        "brand.exemplu.test/robots.txt": robots(),
        "brand.exemplu.test/x": (301, {"location": destinatie}, b""),
    })  # fmt: skip
    e = refuza(desc(site), "https://brand.exemplu.test/x")
    assert e.cod in coduri, e.cod
    assert site.cai() == ["brand.exemplu.test/robots.txt", "brand.exemplu.test/x"]


def test_redirectionarile_in_acelasi_domeniu_se_urmeaza_dar_cel_mult_de_cateva_ori() -> None:
    site = Site({
        "brand.exemplu.test/robots.txt": robots(),
        "brand.exemplu.test/vechi": (301, {"location": "https://www.brand.exemplu.test/nou"}, b""),
        "www.brand.exemplu.test/robots.txt": robots(),
        "www.brand.exemplu.test/nou": html("pagina nouă " * 10),
        **{f"brand.exemplu.test/r{i}": (302, {"location": f"/r{i + 1}"}, b"") for i in range(10)},
    })  # fmt: skip
    r = desc(site).ia_pagina("https://brand.exemplu.test/vechi")
    assert r.url == "https://www.brand.exemplu.test/nou" and r.redirecturi == 1
    assert refuza(desc(site, max_redirecturi=3), "https://brand.exemplu.test/r0").cod == "redirect_prea_multe"


def test_o_gazda_care_isi_schimba_adresa_intre_cereri_este_reverificata() -> None:
    adrese = iter([[PUBLIC], [PUBLIC], ["10.0.0.9"]])
    site = Site(
        {
            "brand.exemplu.test/robots.txt": robots(),
            "brand.exemplu.test/a": html("a" * 100),
            "brand.exemplu.test/b": html("b" * 100),
        }
    )
    c = Ceas()
    d = Descarcator(
        user_agent=UA, radacina="https://brand.exemplu.test/", limite=Limite(pauza_sec=0.0), transport=httpx.MockTransport(site),
        rezolva=lambda g, p: next(adrese), ceas=c, dormi=c.dormi,
    )  # fmt: skip
    assert d.ia_pagina("https://brand.exemplu.test/a").cod == 200  # rezolvări: pentru a (1), robots (2)
    assert refuza(d, "https://brand.exemplu.test/b").cod == "adresa_privata"  # alt DNS, acum privat


def test_robots_txt_interzice_o_parte_si_pagina_interzisa_nu_se_cere_niciodata() -> None:
    site = Site(
        {"brand.exemplu.test/robots.txt": robots(), "brand.exemplu.test/privat/oferta": html("secret " * 20)}
    )
    e = refuza(desc(site), "https://brand.exemplu.test/privat/oferta")
    assert e.cod == "robots_interzis"
    assert site.cai() == ["brand.exemplu.test/robots.txt"]


def test_robots_txt_se_cere_o_singura_data_pe_gazda() -> None:
    site = Site(
        {
            "brand.exemplu.test/robots.txt": robots(),
            "brand.exemplu.test/a": html("a" * 100),
            "brand.exemplu.test/b": html("b" * 100),
        }
    )
    d = desc(site)
    d.ia_pagina("https://brand.exemplu.test/a")
    d.ia_pagina("https://brand.exemplu.test/b")
    assert site.cai().count("brand.exemplu.test/robots.txt") == 1


@pytest.mark.parametrize(
    ("cod", "permis"), [(404, True), (410, True), (401, False), (403, False), (500, False), (503, False)]
)
def test_fara_robots_txt_404_permite_iar_erorile_si_autentificarea_opresc(cod: int, permis: bool) -> None:
    site = Site(
        {
            "brand.exemplu.test/robots.txt": (cod, {"content-type": "text/plain"}, b"x"),
            "brand.exemplu.test/a": html("a" * 100),
        }
    )
    d = desc(site)
    if permis:
        assert d.ia_pagina("https://brand.exemplu.test/a").cod == 200
    else:
        assert refuza(d, "https://brand.exemplu.test/a").cod == "robots_interzis"
        assert "brand.exemplu.test/a" not in site.cai()


def test_crawl_delay_si_pauza_configurata_se_respecta_intre_cereri_pe_aceeasi_gazda() -> None:
    site = Site({
        "brand.exemplu.test/robots.txt": robots("User-agent: *\nCrawl-delay: 4\n"),
        "brand.exemplu.test/a": html("a" * 100), "brand.exemplu.test/b": html("b" * 100),
    })  # fmt: skip
    c = Ceas()
    d = desc(site, c, pauza_sec=1.0)
    d.ia_pagina("https://brand.exemplu.test/a")
    d.ia_pagina("https://brand.exemplu.test/b")
    # robots.txt, apoi a, apoi b: între oricare două cereri cel puțin 4 secunde (Crawl-delay > pauza de 1 s)
    assert c.pauze == [4.0, 4.0]
    # fără Crawl-delay se aplică pauza configurată
    site2 = Site({"brand.exemplu.test/robots.txt": robots(), "brand.exemplu.test/a": html("a" * 100)})
    c2 = Ceas()
    desc(site2, c2, pauza_sec=1.5).ia_pagina("https://brand.exemplu.test/a")
    assert c2.pauze == [1.5]


def test_limita_de_octeti_se_aplica_in_flux_fara_a_citi_tot_corpul() -> None:
    citite: list[int] = []

    def flux() -> Iterator[bytes]:
        for i in range(100):
            citite.append(i)
            yield b"a" * 100_000

    def mare(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=flux())

    site = Site({"brand.exemplu.test/robots.txt": robots(), "brand.exemplu.test/mare": mare})
    e = refuza(desc(site, max_octeti_pagina=250_000), "https://brand.exemplu.test/mare")
    assert e.cod == "prea_mare" and len(citite) <= 4  # s-a oprit după depășire, nu a citit cele 10 MB


def test_dimensiunea_declarata_prea_mare_refuza_fara_sa_citeasca_corpul() -> None:
    site = Site({
        "brand.exemplu.test/robots.txt": robots(),
        "brand.exemplu.test/mare": (200, {"content-type": "text/html", "content-length": "99999999"}, b"x"),
    })  # fmt: skip
    assert refuza(desc(site), "https://brand.exemplu.test/mare").cod == "prea_mare"


def test_o_bomba_de_compresie_este_oprita_la_limita_de_octeti_decodati() -> None:
    bomba = gzip.compress(b"a" * 20_000_000)
    assert len(bomba) < 50_000  # mic pe fir, uriaș după decodare
    site = Site({
        "brand.exemplu.test/robots.txt": robots(),
        "brand.exemplu.test/bomba": (200, {"content-type": "text/html", "content-encoding": "gzip"}, bomba),
    })  # fmt: skip
    assert (
        refuza(desc(site, max_octeti_pagina=500_000), "https://brand.exemplu.test/bomba").cod == "prea_mare"
    )


@pytest.mark.parametrize(
    "tip", ["image/png", "application/pdf", "application/octet-stream", "application/zip", ""]
)
def test_tipurile_de_continut_nepermise_se_refuza_inainte_de_citirea_corpului(tip: str) -> None:
    site = Site(
        {
            "brand.exemplu.test/robots.txt": robots(),
            "brand.exemplu.test/f": (200, {"content-type": tip}, b"x" * 100),
        }
    )
    assert refuza(desc(site), "https://brand.exemplu.test/f").cod == "tip_continut"


@pytest.mark.parametrize(
    ("cod", "motiv"),
    [(401, "autentificare"), (403, "autentificare"), (404, "lipsa"), (410, "lipsa"), (429, "limitat_de_server"),
     (503, "limitat_de_server"), (500, "eroare_server"), (418, "cod_neasteptat")],
)  # fmt: skip
def test_codurile_http_devin_motive_de_sarire(cod: int, motiv: str) -> None:
    site = Site(
        {
            "brand.exemplu.test/robots.txt": robots(),
            "brand.exemplu.test/p": (cod, {"content-type": "text/plain"}, b"x"),
        }
    )
    assert refuza(desc(site), "https://brand.exemplu.test/p").cod == motiv


def test_cererea_conditionata_intoarce_304_iar_etag_se_trimite() -> None:
    def p(c: httpx.Request) -> httpx.Response:
        if c.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(
            200, headers={"content-type": "text/html", "etag": '"v1"'}, content=b"<p>" + b"x" * 80
        )

    site = Site({"brand.exemplu.test/robots.txt": robots(), "brand.exemplu.test/p": p})
    d = desc(site)
    assert d.ia_pagina("https://brand.exemplu.test/p").antete["etag"] == '"v1"'
    r = d.ia_pagina("https://brand.exemplu.test/p", etag='"v1"')
    assert r.cod == 304 and r.corp == b""


def test_timeout_si_erori_de_retea_devin_motive_nu_exceptii() -> None:
    def lent(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("prea lent")

    def cazut(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refuzat")

    site = Site(
        {
            "brand.exemplu.test/robots.txt": robots(),
            "brand.exemplu.test/lent": lent,
            "brand.exemplu.test/cazut": cazut,
        }
    )
    d = desc(site)
    assert refuza(d, "https://brand.exemplu.test/lent").cod == "timeout"
    assert refuza(d, "https://brand.exemplu.test/cazut").cod == "eroare_retea"


def test_adrese_nepermise_la_prima_cerere_nu_ajung_la_retea() -> None:
    site = Site({})
    d = desc(site)
    for url, cod in (
        ("ftp://brand.exemplu.test/", "schema_nepermisa"), ("http://localhost/", "adresa_privata"),
        ("http://user:p@brand.exemplu.test/", "url_cu_credentiale"), ("https://alt-domeniu.test/", "alt_domeniu"),
        ("https://intern.brand.exemplu.test/", "adresa_privata"),
    ):  # fmt: skip
        assert refuza(d, url).cod == cod
    assert site.cereri == []


def test_nu_se_trimit_cookie_uri_chiar_daca_serverul_le_seteaza() -> None:
    site = Site({
        "brand.exemplu.test/robots.txt": robots(),
        "brand.exemplu.test/a": (200, {"content-type": "text/html", "set-cookie": "sesiune=abc; Path=/"}, b"<p>" + b"a" * 90),
        "brand.exemplu.test/b": html("b" * 100),
    })  # fmt: skip
    d = desc(site)
    d.ia_pagina("https://brand.exemplu.test/a")
    d.ia_pagina("https://brand.exemplu.test/b")
    assert all("cookie" not in c.headers for c in site.cereri)
