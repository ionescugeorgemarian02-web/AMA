"""Verificatorul determinist al citatelor (F4.6, docs/09 §9.3): o propunere de fapt este acceptată doar dacă
citatul ei
se regăsește LITERAL în pasaj, iar cifrele afirmate apar în citat. Nucleu pur, fără model și fără bază.

„Literal” înseamnă potrivire exactă de subșir, cu patru normalizări care nu schimbă sensul: forma Unicode
(NFC), spațiile
(orice grup de spații, tab-uri, rânduri noi devine un spațiu), ghilimelele și liniile tipografice (“ ” „ ’ –
—) devin cele
simple, iar sedila devine virgula (ş → ș, ţ → ț: aceeași literă, codificare diferită). Nu se ignoră
majusculele, diacriticele
sau cuvintele: un citat „îmbunătățit” de model nu trece.
"""

import re
import unicodedata
from decimal import Decimal, InvalidOperation

CITAT_MINIM = 8
CITAT_MAXIM = 800
_TIPOGRAFIE = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "„": '"',
        "«": '"',
        "»": '"',
        "’": "'",
        "‘": "'",
        "–": "-",
        "—": "-",
        "−": "-",
        "ş": "ș",
        "Ş": "Ș",
        "ţ": "ț",
        "Ţ": "Ț",
        "\xa0": " ",
        "​": "",
    }
)
NUMAR = re.compile(r"\d+(?:[.\s]\d{3})+(?:,\d+)?|\d+[.,]\d+|\d+")


def normalizeaza(text: str) -> str:
    t = unicodedata.normalize("NFC", text).translate(_TIPOGRAFIE)
    return re.sub(r"\s+", " ", t).strip()


def citat_in_text(citat: str, text: str) -> bool:
    c = normalizeaza(citat)
    return len(c) >= CITAT_MINIM and c in normalizeaza(text)


def numere_din(text: str) -> set[Decimal]:
    """Numerele dintr-un text, în formă canonică (`1.200,50` = `1200.5`; `49` = `49,00`)."""
    gasite: set[Decimal] = set()
    for m in NUMAR.finditer(normalizeaza(text)):
        brut = m.group(0)
        if re.fullmatch(r"\d+(?:[.\s]\d{3})+(?:,\d+)?", brut):
            brut = brut.replace(".", "").replace(" ", "").replace(",", ".")
        else:
            brut = brut.replace(",", ".")
        try:
            gasite.add(Decimal(brut).normalize())
        except InvalidOperation:
            continue
    return gasite


def numar_canonic(valoare: str) -> Decimal | None:
    try:
        return Decimal(valoare.strip().replace(",", ".")).normalize()
    except InvalidOperation:
        return None


def verifica_propunere(citat: str, text_pasaj: str, *, valoare_numar: str | None = None) -> str | None:
    """`None` dacă propunerea trece; altfel codul motivului respingerii:
    `citat_scurt` / `citat_lung`, `citat_negasit` (nu apare literal în pasaj), `valoare_invalida`,
    `valoare_absenta_din_citat` (numărul afirmat nu apare în citat)."""
    c = normalizeaza(citat)
    if len(c) < CITAT_MINIM:
        return "citat_scurt"
    if len(c) > CITAT_MAXIM:
        return "citat_lung"
    if c not in normalizeaza(text_pasaj):
        return "citat_negasit"
    if valoare_numar is not None and valoare_numar.strip():
        v = numar_canonic(valoare_numar)
        if v is None:
            return "valoare_invalida"
        if v not in numere_din(c):
            return "valoare_absenta_din_citat"
    return None
