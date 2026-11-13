"""Apărarea SSRF a colectorului (docs/21 §21.4): ce adrese are voie să atingă platforma. Nucleu pur.

Regulile: doar `http` / `https`; fără date de autentificare în adresă; doar porturile permise (80 și 443,
plus cele date explicit); numele gazdei se rezolvă și TOATE adresele rezultate trebuie să fie publice
(refuzăm și când doar una e privată: un nume cu răspunsuri mixte este o capcană clasică); adresele
loopback, private, link-local (inclusiv metadatele cloud 169.254.169.254), CGNAT, multicast, rezervate,
documentare și cele IPv6 care ascund o adresă IPv4 (mapată, 6to4, Teredo, NAT64) sunt refuzate.
Verificarea se repetă la FIECARE redirecționare (o face descărcătorul).

`exceptii`: adrese permise explicit. Folosit DOAR în teste (serverul local fals); descărcătorul refuză să
primească o excepție în afara mediului `test`.
"""

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit

SCHEME_PERMISE = ("http", "https")
PORTURI_IMPLICITE = frozenset({80, 443})
NUME_INTERNE = ("localhost", "metadata", "metadata.google.internal")
SUFIXE_INTERNE = (".local", ".localhost", ".internal", ".intranet", ".lan", ".home", ".corp")
LUNGIME_MAXIMA_URL = 2000

Rezolvator = Callable[[str, int], list[str]]


class UrlRefuzat(Exception):
    """Adresa nu are voie să fie citită. `cod` este un motiv stabil (vezi `colectare.MOTIVE`)."""

    def __init__(self, cod: str, detaliu: str = "") -> None:
        super().__init__(f"{cod}: {detaliu}" if detaliu else cod)
        self.cod = cod


@dataclass(frozen=True)
class UrlValid:
    schema: str
    gazda: str  # minuscule, fără punct final
    port: int
    cale: str  # cale + interogare, începe cu „/”


def adresa_publica(adresa: str, exceptii: Iterable[str] = ()) -> bool:
    """`True` doar dacă adresa este rutabilă public (sau e o excepție explicită)."""
    try:
        ip = ipaddress.ip_address(adresa.split("%", 1)[0])
    except ValueError:
        return False
    if str(ip) in set(exceptii):
        return True
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return adresa_publica(str(ip.ipv4_mapped), exceptii)
        if ip.sixtofour is not None or ip.teredo is not None:
            return False
        if ip in ipaddress.ip_network("64:ff9b::/96") or ip in ipaddress.ip_network("64:ff9b:1::/48"):
            return False  # NAT64: ascunde o adresă IPv4
        if ip in ipaddress.ip_network("100::/64"):
            return False
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    ):
        return False
    return not (isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("192.0.0.0/24"))


def valideaza_url(url: str, *, porturi: Iterable[int] = PORTURI_IMPLICITE) -> UrlValid:
    """Verifică partea sintactică a adresei. Ridică `UrlRefuzat`."""
    if len(url) > LUNGIME_MAXIMA_URL or any(c in url for c in "\r\n\t\x00 "):
        raise UrlRefuzat("url_invalid", "lungime sau caractere de control")
    try:
        p = urlsplit(url)
        port = p.port
    except ValueError:
        raise UrlRefuzat("url_invalid", "nu se poate interpreta") from None
    if p.scheme.lower() not in SCHEME_PERMISE:
        raise UrlRefuzat("schema_nepermisa", p.scheme.lower() or "fără schemă")
    if p.username is not None or p.password is not None or "@" in (p.netloc or ""):
        raise UrlRefuzat("url_cu_credentiale")
    gazda = (p.hostname or "").lower().rstrip(".")
    if not gazda:
        raise UrlRefuzat("url_invalid", "fără gazdă")
    if gazda in NUME_INTERNE or gazda.endswith(SUFIXE_INTERNE):
        raise UrlRefuzat("adresa_privata", gazda)
    if port is None:
        port = 443 if p.scheme.lower() == "https" else 80
    if port not in set(porturi):
        raise UrlRefuzat("port_nepermis", str(port))
    cale = p.path or "/"
    if p.query:
        cale += "?" + p.query
    return UrlValid(p.scheme.lower(), gazda, port, cale)


def rezolva_sistem(gazda: str, port: int) -> list[str]:
    """Rezolvarea DNS reală (`getaddrinfo`). Înlocuibilă în teste."""
    try:
        info = socket.getaddrinfo(gazda, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise UrlRefuzat("dns_esuat", gazda) from None
    adrese: list[str] = []
    for fam, _t, _p, _c, sock in info:
        if fam in (socket.AF_INET, socket.AF_INET6) and str(sock[0]) not in adrese:
            adrese.append(str(sock[0]))
    return adrese


def adrese_sigure(
    url: UrlValid, rezolva: Rezolvator = rezolva_sistem, exceptii: Iterable[str] = ()
) -> list[str]:
    """Adresele spre care are voie să se conecteze descărcătorul pentru `url` (toate publice), în ordinea
    rezolvării. O gazdă care este deja o adresă IP se verifică direct. Ridică `UrlRefuzat("adresa_privata")`
    dacă ORICARE dintre adrese nu e publică."""
    try:
        ipaddress.ip_address(url.gazda.strip("[]"))
        adrese = [url.gazda.strip("[]")]
    except ValueError:
        adrese = rezolva(url.gazda, url.port)
    if not adrese:
        raise UrlRefuzat("dns_esuat", url.gazda)
    exceptii = tuple(exceptii)
    nepublice = [a for a in adrese if not adresa_publica(a, exceptii)]
    if nepublice:
        raise UrlRefuzat("adresa_privata", f"{url.gazda} -> {nepublice[0]}")
    return adrese
