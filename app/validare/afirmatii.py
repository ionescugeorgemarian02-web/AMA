"""Extragerea DETERMINISTĂ a afirmațiilor verificabile dintr-un text (G2, docs/09 §9.3). Nucleu pur.

Tipuri: `pret` (număr + monedă), `procent`, `termen` („în 24 de ore”, „3 zile”), `data`, `ora` (11:00),
`cifra` (alt număr
despre client), `superlativ`, `comparatie`, `promisiune` (liste în `date/afirmatii.toml`). Fiecare afirmație
păstrează
fragmentul EXACT din text și poziția lui; numerele se normalizează cu `creier.citat` (1.200,50 = 1200,5), nu
cu un model.
Adresele, hashtag-urile și adresele de email nu sunt afirmații (se maschează înainte, păstrând pozițiile).
"""

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from app.creier import citat
from app.validare import text_ro
from app.validare.date_validare import incarca

NUM = r"\d+(?:[.\s ]\d{3})+(?:,\d+)?|\d+[.,]\d+|\d+"
_NUM_G = f"(?:{NUM})"
PRET_DUPA = re.compile(
    rf"(?P<n>{_NUM_G})\s*(?P<m>lei|leu|ron|euro|eur|usd|dolari|dolar|€|\$)(?![a-z])", re.IGNORECASE
)
PRET_INAINTE = re.compile(rf"(?P<m>€|\$|\bron\b|\beur\b|\busd\b)\s*(?P<n>{_NUM_G})", re.IGNORECASE)
PROCENT = re.compile(rf"(?P<n>{_NUM_G})\s*(?:%|procente\b|procent\b|la suta\b)", re.IGNORECASE)
TERMEN = re.compile(
    rf"(?P<n>{_NUM_G})(?:\s*[-–]\s*(?P<n2>{_NUM_G}))?\s*(?:de\s+)?"
    r"(?P<u>zile|zi|ore|ora|minute|minut|saptamani|saptamana|luni|luna|ani|an)\b",
    re.IGNORECASE,
)
DATA_NUMERICA = re.compile(r"\b(?P<z>\d{1,2})[./](?P<l>\d{1,2})[./](?P<a>(?:19|20)\d{2})\b")
DATA_TEXT = re.compile(
    r"\b(?P<z>\d{1,2})\s+(?P<l>ianuarie|februarie|martie|aprilie|mai|iunie|iulie|august|septembrie|octombrie|"
    r"noiembrie|decembrie)(?:\s+(?P<a>(?:19|20)\d{2}))?\b",
    re.IGNORECASE,
)
DIN_ANUL = re.compile(r"\bdin\s+(?:anul\s+)?(?P<a>(?:19|20)\d{2})\b", re.IGNORECASE)
ORA = re.compile(r"(?<![\d:])(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d)(?![\d:])")
CIFRA = re.compile(rf"(?<![\w.,])(?P<n>{_NUM_G})(?![\w]*(?:[.,]\d))", re.IGNORECASE)
INCEPUT_LISTA = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
CUVANT_URMATOR = re.compile(r"\s*(?:de\s+)?([a-z]+)")
CUVANT_ANTERIOR = re.compile(r"(?<![a-z-])([a-z][a-z-]*)\s*(?:nr\.?\s*)?$")


@dataclass(frozen=True)
class Afirmatie:
    tip: str  # pret | procent | termen | data | ora | cifra | superlativ | comparatie | promisiune
    fragment: str  # exact din text
    start: int
    sfarsit: int
    valoare: Decimal | None = None
    moneda: str | None = None  # RON | EUR | USD
    unitate: str | None = None  # rădăcina unității de timp
    data: tuple[int, int, int | None] | None = None  # (zi, lună, an) sau (0, 0, an) pentru „din 2019”
    ora: str | None = None  # „11:00”
    cuvinte: tuple[
        str, ...
    ] = ()  # rădăcinile cuvintelor semnificative (superlativ / comparație / promisiune)


def baza(text: str) -> str:
    """Litere mici, fără diacritice, ACEEAȘI lungime ca textul (poziții păstrate)."""
    iesire = []
    for c in text.lower():
        d = unicodedata.normalize("NFD", c)
        iesire.append(d[0] if d else c)
    return "".join(iesire)


def mascheaza_adrese(text: str) -> str:
    """Înlocuiește linkurile, emailurile și hashtag-urile cu spații de aceeași lungime."""
    for sablon in (text_ro.URL, text_ro.URL_STRICAT, text_ro.EMAIL, text_ro.HASHTAG):
        text = sablon.sub(lambda m: " " * len(m.group(0)), text)
    return text


def numar(token: str) -> Decimal | None:
    gasite = citat.numere_din(token)
    return next(iter(gasite)) if len(gasite) == 1 else None


def moneda_cod(cuvant: str) -> str | None:
    c = cuvant.lower()
    for cod, forme in incarca("afirmatii")["moneda"].items():
        if c in forme:
            return str(cod)
    return None


def _liber(ocupat: list[tuple[int, int]], s: int, e: int) -> bool:
    return all(e <= a or s >= b for a, b in ocupat)


def _radacini(expresie: str) -> tuple[str, ...]:
    cfg = incarca("afirmatii")["acoperire"]
    goale = set(cfg["cuvinte_goale"])
    n = int(cfg["radacina"])
    cuvinte = re.findall(r"[a-z]{3,}", expresie)
    return tuple(dict.fromkeys(c[:n] for c in cuvinte if c not in goale))


def extrage(text: str) -> list[Afirmatie]:
    """Afirmațiile verificabile din `text`, în ordinea apariției."""
    mascat = mascheaza_adrese(text)
    b = baza(mascat)
    cfg = incarca("afirmatii")
    ocupat: list[tuple[int, int]] = []
    gasite: list[Afirmatie] = []

    def adauga(a: Afirmatie) -> None:
        if _liber(ocupat, a.start, a.sfarsit):
            ocupat.append((a.start, a.sfarsit))
            gasite.append(a)

    def fragment(m: re.Match[str]) -> tuple[int, int, str]:
        return m.start(), m.end(), mascat[m.start() : m.end()]

    for m in PRET_DUPA.finditer(b):
        s, e, f = fragment(m)
        v = numar(m.group("n"))
        if v is not None:
            adauga(Afirmatie("pret", f, s, e, valoare=v, moneda=moneda_cod(m.group("m"))))
    for m in PRET_INAINTE.finditer(b):
        s, e, f = fragment(m)
        v = numar(m.group("n"))
        if v is not None:
            adauga(Afirmatie("pret", f, s, e, valoare=v, moneda=moneda_cod(m.group("m"))))
    for m in PROCENT.finditer(b):
        s, e, f = fragment(m)
        v = numar(m.group("n"))
        if v is not None:
            adauga(Afirmatie("procent", f, s, e, valoare=v))
    for m in DATA_NUMERICA.finditer(b):
        s, e, f = fragment(m)
        adauga(Afirmatie("data", f, s, e, data=(int(m.group("z")), int(m.group("l")), int(m.group("a")))))
    for m in DATA_TEXT.finditer(b):
        s, e, f = fragment(m)
        luna = cfg["luni_an"][m.group("l")]
        an = int(m.group("a")) if m.group("a") else None
        adauga(Afirmatie("data", f, s, e, data=(int(m.group("z")), luna, an)))
    for m in DIN_ANUL.finditer(b):
        s, e, f = fragment(m)
        adauga(Afirmatie("data", f, s, e, data=(0, 0, int(m.group("a")))))
    for m in ORA.finditer(b):
        s, e, f = fragment(m)
        adauga(Afirmatie("ora", f, s, e, ora=f"{int(m.group('h')):02d}:{m.group('m')}"))
    unitati = cfg["unitati_timp"]
    for m in TERMEN.finditer(b):
        s, e, f = fragment(m)
        for grup in ("n", "n2"):
            if m.group(grup):
                v = numar(m.group(grup))
                if v is not None:
                    # un interval produce două afirmații cu același fragment; se păstrează un singur
                    # interval ocupat
                    a = Afirmatie("termen", f, s, e, valoare=v, unitate=unitati[m.group("u")])
                    if grup == "n":
                        adauga(a)
                    elif gasite and gasite[-1].start == s:
                        gasite.append(a)
    for sectiune, tip in (
        ("superlative", "superlativ"),
        ("comparatii", "comparatie"),
        ("promisiuni", "promisiune"),
    ):
        for expresie in cfg[sectiune]["expresii"]:
            for m in re.finditer(expresie, b):
                s, e, f = fragment(m)
                adauga(Afirmatie(tip, f, s, e, cuvinte=_radacini(b[s:e])))
    neutre = set(cfg["cifre_neutre"]["cuvinte"])
    etichete = set(cfg["cifre_neutre"].get("etichete", ()))
    inceputuri_liste = {m.start() for m in INCEPUT_LISTA.finditer(b)}
    for m in CIFRA.finditer(b):
        s, e, f = fragment(m)
        v = numar(m.group("n"))
        if v is None or any(s <= i + 1 <= e or i <= s <= i + 4 for i in inceputuri_liste):
            continue
        anterior = CUVANT_ANTERIOR.search(b[max(0, s - 30) : s])
        if anterior and anterior.group(1) in etichete:
            continue
        urmator = CUVANT_URMATOR.match(b, e)
        if urmator and urmator.group(1) in neutre:
            continue
        if v == v.to_integral_value() and 1900 <= v <= 2100 and "." not in f and "," not in f:
            continue  # un an singur nu este o afirmație despre client („din 2019” se prinde la dată)
        adauga(Afirmatie("cifra", f, s, e, valoare=v))
    return sorted(gasite, key=lambda a: (a.start, a.tip))
