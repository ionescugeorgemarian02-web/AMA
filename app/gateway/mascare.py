"""Garda de date personale (G12, 8.9, 21.6): mascarea deterministă înainte de orice apel extern.

Detectoare deterministe pentru România (fără model, fără rețea): email, IBAN (mod 97), număr de card
(Luhn), CNP (cifră de control și dată plauzibilă), telefon românesc, adrese IP (v4 și v6) și, DOAR dacă
apelul o cere, CUI/CIF (cu cifră de control, după cuvântul „CUI”/„CIF”/„cod fiscal” sau cu prefixul RO).
Fiecare valoare devine un marcaj stabil în cadrul unui apel (`[EMAIL_1]`: aceeași valoare, același
marcaj), iar răspunsul poate fi demascat la cerere.

Ce NU face: nu recunoaște nume proprii, adrese poștale sau alte date personale fără structură fixă (ar
cere un model; rămân în sarcina apelantului să nu le trimită). Detectoarele sunt prudente: o cifră de
control greșită nu se maschează (un număr oarecare nu e CNP), deci pot exista fals-negative la date scrise
cu greșeli.
"""

import ipaddress
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

TIPURI = ("EMAIL", "IBAN", "CNP", "CARD", "IP", "TELEFON", "CUI")  # și ordinea priorității la suprapunere
MARCAJ_FALS = re.compile(r"\[(" + "|".join(TIPURI) + r")_(\d+)\]")

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
IBAN_CANDIDAT = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{2,4}){3,8}\b")
CNP_CANDIDAT = re.compile(r"(?<!\d)[1-9]\d{12}(?!\d)")
CARD_CANDIDAT = re.compile(r"(?<![\d\-])\d(?:[ \-]?\d){12,18}(?![\d\-])")
IPV4 = re.compile(
    r"(?<!\d)(?<!\d\.)(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?!\d)(?!\.\d)"
)
IPV6 = re.compile(r"(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])")
TELEFON = re.compile(r"(?<![\d+])(?:(?:\+|00)40|0)[\s.\-()]*[2-37](?:[\s.\-()]*\d){8}(?!\d)")
# Identificatorii (UUID, ex. `[afirmatie:<uuid>]` din prompturi) nu sunt date personale. Cifrele lor,
# despărțite
# prin `-`, imitau un card (13–19 cifre cu Luhn valid, ~0,3% din UUIDv7) sau un telefon, iar marcajul de
# trimitere ajungea mascat în prompt: modelul nu mai putea cita sursa.
UUID = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}(?![0-9A-Fa-f])")
CUI_CUVANT = re.compile(r"(?i)\b(?:CUI|CIF|cod fiscal)\s*:?\s*(?:RO\s?)?(\d{2,10})\b")
CUI_RO = re.compile(r"\bRO\s?(\d{2,10})\b")

LUNGIME_IBAN = {
    "RO": 24, "MD": 24, "DE": 22, "FR": 27, "IT": 27, "ES": 24, "GB": 22, "NL": 18, "AT": 20,
    "BG": 22, "HU": 28, "PL": 28, "CZ": 24, "SK": 24, "GR": 27, "PT": 25, "BE": 16, "IE": 22,
}  # fmt: skip
COD_JUDET_CNP = set(range(1, 53)) | {70}
PONDERI_CNP = (2, 7, 9, 1, 4, 6, 3, 5, 8, 2, 7, 9)
PONDERI_CUI = (7, 5, 3, 2, 1, 7, 5, 3, 2)


def luhn_valid(cifre: str) -> bool:
    if not cifre.isdigit() or not 13 <= len(cifre) <= 19:
        return False
    total = 0
    for i, c in enumerate(reversed(cifre)):
        n = int(c)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def iban_valid(iban: str) -> bool:
    iban = iban.replace(" ", "")
    lung = LUNGIME_IBAN.get(iban[:2])
    if not 15 <= len(iban) <= 34 or (lung is not None and len(iban) != lung) or not iban.isalnum():
        return False
    mutat = iban[4:] + iban[:4]
    numeric = "".join(str(int(c, 36)) for c in mutat)
    return int(numeric) % 97 == 1


def cnp_valid(cnp: str) -> bool:
    if not (len(cnp) == 13 and cnp.isdigit() and cnp[0] != "0"):
        return False
    suma = sum(int(c) * p for c, p in zip(cnp[:12], PONDERI_CNP, strict=True)) % 11
    control = 1 if suma == 10 else suma
    if control != int(cnp[12]):
        return False
    if int(cnp[7:9]) not in COD_JUDET_CNP:
        return False
    s, aa, ll, zz = int(cnp[0]), int(cnp[1:3]), int(cnp[3:5]), int(cnp[5:7])
    secol = {1: 1900, 2: 1900, 3: 1800, 4: 1800, 5: 2000, 6: 2000}.get(s)
    if secol is None:  # 7, 8, 9: rezidenți și străini; anul nu se deduce din cifra de sex
        secol = 1900 if aa > 30 else 2000
    try:
        date(secol + aa, ll, zz)
    except ValueError:
        return False
    return True


def cui_valid(cifre: str) -> bool:
    if not (cifre.isdigit() and 2 <= len(cifre) <= 10):
        return False
    corp, control = cifre[:-1].zfill(9), int(cifre[-1])
    suma = sum(int(c) * p for c, p in zip(corp, PONDERI_CUI, strict=True)) * 10 % 11
    return (0 if suma == 10 else suma) == control


def telefon_valid(brut: str) -> bool:
    d = re.sub(r"\D", "", brut)
    if d.startswith("0040"):
        rest = d[4:]
    elif brut.lstrip().startswith("+") and d.startswith("40"):
        rest = d[2:]
    elif d.startswith("0"):
        rest = d[1:]
    else:
        return False
    return len(rest) == 9 and rest[0] in "237"


@dataclass(frozen=True)
class Detectie:
    tip: str
    start: int
    sfarsit: int
    valoare: str


def _candidati(text: str, cui: bool) -> list[Detectie]:
    gasite: list[Detectie] = []
    for m in EMAIL.finditer(text):
        gasite.append(Detectie("EMAIL", m.start(), m.end(), m.group()))
    for m in IBAN_CANDIDAT.finditer(text):
        grupuri = m.group().split(" ")
        # grupurile de după IBAN (cuvinte cu majuscule) nu fac parte din el: se încearcă prefixe tot mai
        # scurte
        for k in range(len(grupuri), 0, -1):
            candidat = " ".join(grupuri[:k])
            if iban_valid(candidat):
                gasite.append(Detectie("IBAN", m.start(), m.start() + len(candidat), candidat))
                break
    for m in CNP_CANDIDAT.finditer(text):
        if cnp_valid(m.group()):
            gasite.append(Detectie("CNP", m.start(), m.end(), m.group()))
    for m in CARD_CANDIDAT.finditer(text):
        if luhn_valid(re.sub(r"\D", "", m.group())):
            gasite.append(Detectie("CARD", m.start(), m.end(), m.group()))
    for m in IPV4.finditer(text):
        gasite.append(Detectie("IP", m.start(), m.end(), m.group()))
    for m in IPV6.finditer(text):
        try:
            ipaddress.IPv6Address(m.group())
        except ValueError:
            continue
        gasite.append(Detectie("IP", m.start(), m.end(), m.group()))
    for m in TELEFON.finditer(text):
        if telefon_valid(m.group()):
            gasite.append(Detectie("TELEFON", m.start(), m.end(), m.group()))
    if cui:
        for rx in (CUI_CUVANT, CUI_RO):
            for m in rx.finditer(text):
                if cui_valid(m.group(1)):
                    gasite.append(Detectie("CUI", m.start(), m.end(), m.group()))
    return gasite


def detecteaza(text: str, *, cui: bool = False) -> list[Detectie]:
    """Detecțiile fără suprapuneri, în ordinea din text. La suprapunere câștigă tipul mai specific
    (ordinea din `TIPURI`), apoi cea mai lungă."""
    prioritate = {t: i for i, t in enumerate(TIPURI)}
    uuid_uri = [(m.start(), m.end()) for m in UUID.finditer(text)]
    alese: list[Detectie] = []
    for d in sorted(
        _candidati(text, cui), key=lambda d: (prioritate[d.tip], -(d.sfarsit - d.start), d.start)
    ):
        if any(d.start < sf and d.sfarsit > st for st, sf in uuid_uri):
            continue  # o detecție care atinge un UUID e o falsă pozitivă
        if all(d.sfarsit <= a.start or d.start >= a.sfarsit for a in alese):
            alese.append(d)
    return sorted(alese, key=lambda d: d.start)


def _normalizat(tip: str, valoare: str) -> str:
    if tip == "EMAIL":
        return valoare.lower()
    if tip in ("IBAN", "CARD", "TELEFON", "CNP", "CUI"):
        return re.sub(r"[\s\-.()]", "", valoare).upper()
    return valoare.lower()


@dataclass
class Masca:
    """Mascarea unui apel: aceeași valoare primește același marcaj în toate mesajele și în răspuns."""

    cui: bool = False
    harta: dict[str, str] = field(
        default_factory=dict
    )  # marcaj -> valoarea originală (prima formă întâlnită)
    _cheie: dict[tuple[str, str], str] = field(default_factory=dict)
    _numere: dict[str, int] = field(default_factory=dict)

    def _marcaj(self, d: Detectie) -> str:
        cheie = (d.tip, _normalizat(d.tip, d.valoare))
        if cheie not in self._cheie:
            self._numere[d.tip] = self._numere.get(d.tip, 0) + 1
            marcaj = f"[{d.tip}_{self._numere[d.tip]}]"
            self._cheie[cheie] = marcaj
            self.harta[marcaj] = d.valoare
        return self._cheie[cheie]

    def text(self, continut: str, *, raspuns: bool = False) -> str:
        """Maschează un text. În intrare, orice ce arată a marcaj i se schimbă parantezele (nu poate
        păcăli demascarea); într-un răspuns rămân marcajele pe care le-am pus noi (modelul le repetă),
        restul se neutralizează."""
        continut = MARCAJ_FALS.sub(
            lambda m: m.group(0) if raspuns and m.group(0) in self.harta else f"({m.group(1)}_{m.group(2)})",
            continut,
        )
        iesire, cursor = [], 0
        for d in detecteaza(continut, cui=self.cui):
            iesire.append(continut[cursor : d.start])
            iesire.append(self._marcaj(d))
            cursor = d.sfarsit
        iesire.append(continut[cursor:])
        return "".join(iesire)

    def json(self, valoare: Any, *, raspuns: bool = False) -> Any:
        """Maschează toate șirurile dintr-o structură JSON (răspunsul se salvează în varianta mascată)."""
        if isinstance(valoare, str):
            return self.text(valoare, raspuns=raspuns)
        if isinstance(valoare, list):
            return [self.json(v, raspuns=raspuns) for v in valoare]
        if isinstance(valoare, dict):
            return {k: self.json(v, raspuns=raspuns) for k, v in valoare.items()}
        return valoare

    def demasca(self, continut: str) -> str:
        return MARCAJ_FALS.sub(lambda m: self.harta.get(m.group(0), m.group(0)), continut)

    def demasca_json(self, valoare: Any) -> Any:
        if isinstance(valoare, str):
            return self.demasca(valoare)
        if isinstance(valoare, list):
            return [self.demasca_json(v) for v in valoare]
        if isinstance(valoare, dict):
            return {k: self.demasca_json(v) for k, v in valoare.items()}
        return valoare

    def rezumat(self) -> dict[str, int]:
        """Câte valori distincte s-au mascat, pe tip (pentru jurnal; fără valorile însele)."""
        return dict(self._numere)
