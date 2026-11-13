"""Adrese: normalizare, domeniul înregistrat și euristici contra capcanelor de linkuri. Nucleu pur."""

import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

# Parametri de urmărire: aceeași pagină, alt link. Se scot la normalizare.
PARAMETRI_URMARIRE = re.compile(
    r"^(utm_.*|fbclid|gclid|msclkid|mc_cid|mc_eid|_ga|ref|igshid)$", re.IGNORECASE
)
# Sufixe publice cu două etichete, frecvente pentru IMM-uri din România și din regiune. NU este lista completă
# (Public Suffix List): pentru un sufix necunoscut, domeniul înregistrat iese prea larg sau prea îngust.
SUFIXE_DUBLE = frozenset(
    {
        "com.ro",
        "org.ro",
        "firme.ro",
        "store.ro",
        "info.ro",
        "nom.ro",
        "nt.ro",
        "rec.ro",
        "arts.ro",
        "tm.ro",
        "co.uk",
        "org.uk",
        "com.au",
        "com.br",
        "co.za",
        "co.in",
        "com.tr",
        "com.pl",
        "com.ua",
        "com.md",
    }
)
EXTENSII_NECITIBILE = re.compile(
    r"\.(jpe?g|png|gif|webp|svg|ico|bmp|avif|mp[34]|mov|avi|webm|zip|rar|7z|gz|tar|exe|dmg|apk|css|js|json|xml"
    r"|woff2?|ttf|otf|eot|docx?|xlsx?|pptx?)$",
    re.IGNORECASE,
)


def normalizeaza(url: str) -> str:
    """Forma canonică: schemă și gazdă cu litere mici, fără port implicit, fără fragment, fără parametri de
    urmărire, parametrii de interogare sortați, fără „/” dublat. Aceeași pagină → același șir."""
    p = urlsplit(url.strip())
    schema = p.scheme.lower()
    gazda = (p.hostname or "").lower().rstrip(".")
    if ":" in gazda:
        gazda = f"[{gazda}]"
    port = p.port
    if port is not None and not ((schema == "http" and port == 80) or (schema == "https" and port == 443)):
        gazda = f"{gazda}:{port}"
    cale = re.sub(r"/{2,}", "/", p.path or "/")
    interogare = urlencode(
        sorted(
            (k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not PARAMETRI_URMARIRE.match(k)
        )
    )
    return urlunsplit((schema, gazda, cale, interogare, ""))


def rezolva_link(baza: str, href: str) -> str | None:
    """Adresa absolută a unui `href` față de pagina `baza`, sau `None` dacă nu e un link web (mailto:, tel:,
    javascript:, ancoră)."""
    href = href.strip()
    if not href or href.startswith("#"):
        return None
    if re.match(r"^(mailto|tel|javascript|data|sms|whatsapp|viber|skype):", href, re.IGNORECASE):
        return None
    try:
        return urljoin(baza, href)
    except ValueError:
        return None


def domeniu_inregistrat(gazda: str) -> str:
    """Domeniul înregistrat al unei gazde (`blog.brand.ro` → `brand.ro`; `brand.com.ro` rămâne
    `brand.com.ro`).
    O adresă IP sau un nume cu o singură etichetă rămâne întreagă."""
    g = gazda.lower().rstrip(".").strip("[]")
    et = g.split(".")
    if len(et) <= 2 or all(e.isdigit() for e in et) or ":" in g:
        return g
    if ".".join(et[-2:]) in SUFIXE_DUBLE:
        return ".".join(et[-3:])
    return ".".join(et[-2:])


def acelasi_domeniu(a: str, b: str) -> bool:
    return domeniu_inregistrat(a) == domeniu_inregistrat(b)


def este_pagina_probabila(url: str) -> bool:
    """Prefiltru ieftin: extensii care nu sunt pagini (imagini, arhive, scripturi) nu se mai cer."""
    return EXTENSII_NECITIBILE.search(urlsplit(url).path) is None


def suspect_de_capcana(url: str, *, max_segmente: int = 12, repetari: int = 3) -> bool:
    """Adrese care miros a capcană de linkuri: cale foarte adâncă, același segment repetat (`/a/a/a/…`), prea
    mulți parametri. Capcanele cu parametri (`?pagina=1..∞`) le oprește și `max_variante_interogare`."""
    p = urlsplit(url)
    segmente = [s for s in p.path.split("/") if s]
    if len(segmente) > max_segmente:
        return True
    if any(segmente.count(s) >= repetari for s in set(segmente)):
        return True
    return len(parse_qsl(p.query)) > 6
