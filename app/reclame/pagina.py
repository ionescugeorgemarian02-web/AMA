"""Citirea paginii de destinație a unei reclame, cu apărarea SSRF (F15.2, docs/21 §21.4).

Linkul reclamei vine de la client; înainte de orice cerere adresa trece prin `cercetare.ssrf` (doar
http/https, porturile 80/443, toate adresele rezolvate publice), iar redirecționările se urmează de mână,
revalidate la
fiecare pas (cel mult `MAX_REDIRECTARI`). # NEVERIFICAT: conexiunea nu e legată de IP-ul validat (rebinding
DNS între validare și conectare); pe VPS ieșirea trece prin aceeași rețea, fără acces la rețeaua internă.
"""

from urllib.parse import urljoin

import httpx

from app.cercetare import ssrf

MAX_REDIRECTARI = 5


def get_sigur(url: str, *, timeout: float = 10.0) -> httpx.Response | None:
    """GET pe o adresă publică; `None` dacă adresa e refuzată, nu răspunde sau redirecționează prea mult."""
    for _ in range(MAX_REDIRECTARI + 1):
        try:
            ssrf.adrese_sigure(ssrf.valideaza_url(url), ssrf.rezolva_sistem)
            r = httpx.get(url, timeout=timeout, follow_redirects=False)
        except (ssrf.UrlRefuzat, httpx.HTTPError):
            return None
        if r.is_redirect and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            continue
        return r
    return None
