"""F4.2 — apărarea SSRF (docs/21 §21.4): ce adrese nu se ating niciodată. Nucleu pur, fără rețea."""

import pytest

from app.cercetare.ssrf import UrlRefuzat, adresa_publica, adrese_sigure, valideaza_url

PUBLICA = "93.184.216.34"


@pytest.mark.parametrize(
    "adresa",
    [
        "127.0.0.1", "127.1.2.3", "10.0.0.5", "172.16.9.9", "172.31.255.255", "192.168.1.1", "169.254.169.254",
        "169.254.0.1", "100.64.0.1", "0.0.0.0",  # noqa: S104 "224.0.0.1", "240.0.0.1", "255.255.255.255", "192.0.0.8",
        "198.18.0.1", "203.0.113.5", "::1", "::", "fe80::1", "fc00::1", "fd12:3456::1", "ff02::1",
        "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254", "2002:7f00:1::1", "64:ff9b::7f00:1",
        "2001:0:4136:e378:8000:63bf:3fff:fdd2", "not-an-ip", "",
    ],
)  # fmt: skip
def test_adresele_private_loopback_link_local_si_metadata_sunt_refuzate(adresa: str) -> None:
    assert adresa_publica(adresa) is False


@pytest.mark.parametrize("adresa", [PUBLICA, "8.8.8.8", "1.1.1.1", "2606:4700:4700::1111", "::ffff:8.8.8.8"])
def test_adresele_publice_trec(adresa: str) -> None:
    assert adresa_publica(adresa) is True


def test_exceptia_explicita_permite_doar_adresa_numita() -> None:
    assert adresa_publica("127.0.0.1", ["127.0.0.1"]) is True
    assert adresa_publica("127.0.0.2", ["127.0.0.1"]) is False
    assert adresa_publica("10.0.0.1", ["127.0.0.1"]) is False


@pytest.mark.parametrize(
    ("url", "cod"),
    [
        ("ftp://exemplu.test/", "schema_nepermisa"),
        ("file:///etc/passwd", "schema_nepermisa"),
        ("gopher://exemplu.test/", "schema_nepermisa"),
        ("javascript:alert(1)", "schema_nepermisa"),
        ("//exemplu.test/", "schema_nepermisa"),
        ("http://utilizator:parola@exemplu.test/", "url_cu_credentiale"),  # pragma: allowlist secret
        ("http://exemplu.test@evil.test/", "url_cu_credentiale"),
        ("http://localhost/", "adresa_privata"),
        ("http://metadata.google.internal/computeMetadata/v1/", "adresa_privata"),
        ("http://baza.internal/", "adresa_privata"),
        ("http://imprimanta.local/", "adresa_privata"),
        ("http://exemplu.test:22/", "port_nepermis"),
        ("http://exemplu.test:6379/", "port_nepermis"),
        ("http://exemplu.test:99999/", "url_invalid"),
        ("http:///fara-gazda", "url_invalid"),
        ("http://exemplu.test/a b", "url_invalid"),
        ("http://exemplu.test/\r\nX: y", "url_invalid"),
        ("http://exemplu.test/" + "a" * 3000, "url_invalid"),
    ],
)  # fmt: skip
def test_adresele_nepermise_sunt_refuzate_inainte_de_orice_cerere(url: str, cod: str) -> None:
    with pytest.raises(UrlRefuzat) as exc:
        valideaza_url(url)
    assert exc.value.cod == cod


def test_adresele_normale_trec_cu_portul_si_calea_corecte() -> None:
    v = valideaza_url("HTTPS://Brand.Exemplu.test./Despre?x=1#ancora")
    assert (v.schema, v.gazda, v.port, v.cale) == (
        "https",
        "brand.exemplu.test",
        443,
        "/despre?x=1".replace("despre", "Despre"),
    )
    assert valideaza_url("http://exemplu.test:8080/", porturi={80, 443, 8080}).port == 8080


def test_toate_adresele_rezolvate_trebuie_sa_fie_publice() -> None:
    v = valideaza_url("https://brand.exemplu.test/")
    assert adrese_sigure(v, lambda g, p: [PUBLICA]) == [PUBLICA]
    with pytest.raises(UrlRefuzat) as exc:  # un nume cu răspuns mixt este o capcană (rebinding)
        adrese_sigure(v, lambda g, p: [PUBLICA, "10.0.0.7"])
    assert exc.value.cod == "adresa_privata"
    with pytest.raises(UrlRefuzat):
        adrese_sigure(v, lambda g, p: ["169.254.169.254"])
    with pytest.raises(UrlRefuzat) as exc2:
        adrese_sigure(v, lambda g, p: [])
    assert exc2.value.cod == "dns_esuat"


@pytest.mark.parametrize("gazda", ["127.0.0.1", "[::1]", "169.254.169.254", "10.1.2.3"])
def test_o_gazda_data_ca_adresa_ip_se_verifica_direct(gazda: str) -> None:
    v = valideaza_url(f"http://{gazda}/")
    with pytest.raises(UrlRefuzat):
        adrese_sigure(v, lambda g, p: pytest.fail("nu trebuie rezolvat prin DNS"))


def test_formele_ciudate_de_ip_sunt_prinse_la_rezolvare() -> None:
    # `2130706433`, `0x7f.1`, `0177.0.0.1` ajung la getaddrinfo ca nume: orice ar întoarce, adresa e verificată
    for forma, rezolvata in (
        ("2130706433", "127.0.0.1"),
        ("0x7f.1", "127.0.0.1"),
        ("0177.0.0.1", "127.0.0.1"),
    ):
        v = valideaza_url(f"http://{forma}/")
        with pytest.raises(UrlRefuzat):
            adrese_sigure(v, lambda g, p, r=rezolvata: [r])
