"""Cercetarea SEO, prima formă (F7.10, C6): grupuri de cuvinte-cheie pe intenție. Nucleu pur, determinist.

Intenția după reguli [I] (cuvinte-semnal în română): informațională, comercială, tranzacțională, locală.
Cu produs și pagină, gruparea folosește intenția și această destinație. Exportul Search Console opțional
oferă impresii și poziții măsurate. Listele vechi fără destinații păstrează gruparea lexicală."""

import csv
import math
import re
from dataclasses import dataclass, field
from typing import TextIO

DIACRITICE = str.maketrans("ăâîșşțţ", "aaisstt")
SEMNALE: dict[str, tuple[str, ...]] = {
    "tranzactionala": ("cumpara", "comanda", "abonament", "livrare", "magazin", "oferta"),
    "comerciala": ("cel mai bun", "cea mai buna", "pret", "preturi", "comparatie", "recenzii", "vs"),
    "informationala": ("cum ", "ce ", "de ce", "ghid", "cand ", "care ", "sfaturi", "pasi"),
}
ORASE = ("bucuresti", "brasov", "cluj", "iasi", "timisoara", "constanta", "sibiu", "oradea")
GOALE = {
    "cum",
    "ce",
    "de",
    "la",
    "si",
    "in",
    "pentru",
    "cel",
    "mai",
    "bun",
    "buna",
    "cea",
    "care",
    "cand",
    "un",
    "o",
    "a",
    "al",
    "ale",
    "cu",
    "pe",
    "din",
    "ghid",
    "sfaturi",
    "pret",
    "preturi",
    "cumpara",
    "comanda",
}


def normal(fraza: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", fraza.lower().translate(DIACRITICE)).split())


def intentie(fraza: str) -> str:
    f = " " + normal(fraza) + " "
    for nume, semnale in SEMNALE.items():
        if any((" " + s) in f for s in semnale):
            return nume
    if any(f" {o} " in f for o in ORASE):
        return "locala"
    return "informationala"


def cap(fraza: str) -> str:
    cuvinte = [c for c in normal(fraza).split() if c not in GOALE and c not in ORASE and len(c) > 2]
    return cuvinte[0][:6] if cuvinte else normal(fraza)[:6]


@dataclass
class Grup:
    intentie: str
    cap: str
    cuvinte: list[str] = field(default_factory=list)

    produs: str | None = None
    pagina: str | None = None
    impresii: int | None = None
    pozitie: float | None = None

    @property
    def principal(self) -> str:
        return self.cuvinte[0]


def grupeaza(cuvinte: list[str], *, produs: str | None = None, pagina: str | None = None) -> list[Grup]:
    if (produs is None) != (pagina is None) or produs == "" or pagina == "":
        raise ValueError("Produsul și pagina se completează împreună.")
    grupuri: dict[tuple[str, str], Grup] = {}
    for c in cuvinte:
        c = " ".join(c.split())
        if not c:
            continue
        k = (intentie(c), produs or cap(c))
        grupuri.setdefault(k, Grup(*k, produs=produs, pagina=pagina)).cuvinte.append(c)
    return list(grupuri.values())


_COLOANE = {
    "interogare": {
        "query",
        "top queries",
        "interogare",
        "interogari",
        "cele mai frecvente interogari",
        "interogari populare",
        "cele mai populare interogari",
    },
    "produs": {"product", "produs"},
    "pagina": {"page", "pagina", "url", "landing page"},
    "impresii": {"impressions", "impresii", "afisari"},
    "pozitie": {"position", "average position", "pozitie", "pozitie medie"},
}


@dataclass
class _Masurare:
    impresii: int = 0
    suma_pozitii: float = 0.0

    @property
    def pozitie(self) -> float | None:
        return self.suma_pozitii / self.impresii if self.impresii else None


def din_csv(fisier: TextIO, *, produs: str = "", pagina: str = "") -> list[Grup]:
    """Importă interogări pentru o singură perioadă, cu metricile GSC opționale.

    Produsul și pagina provin din coloane sau din argumente (export filtrat pe pagina respectivă).
    Agregă rândurile pentru aceeași interogare și destinație, ponderând pozițiile cu impresiile.
    """
    antet = fisier.readline().lstrip("\ufeff")
    separator = ";" if ";" in antet else ","
    coloane = next(csv.reader([antet], delimiter=separator), [])
    aliasuri = {alias: cheie for cheie, valori in _COLOANE.items() for alias in valori}
    campuri = [aliasuri.get(normal(c), c.strip()) for c in coloane]
    if "interogare" not in campuri or len(campuri) != len(set(campuri)):
        raise ValueError("Antetul CSV trebuie să conțină interogarea și coloane distincte.")
    masurat = "impresii" in campuri
    if masurat != ("pozitie" in campuri):
        raise ValueError("Exportul trebuie să conțină atât impresiile, cât și poziția.")
    agregat: dict[tuple[str, str, str], dict[str, _Masurare]] = {}
    for nr, rand in enumerate(csv.DictReader(fisier, fieldnames=campuri, delimiter=separator), start=2):
        if None in rand or None in rand.values():
            raise ValueError(f"Număr de coloane incorect la rândul {nr}.")
        termen = " ".join(rand["interogare"].split())
        nume = (rand.get("produs") or produs).strip()
        url = (rand.get("pagina") or pagina).strip()
        if not termen or not nume or not url:
            raise ValueError(f"Completează interogarea, produsul și pagina la rândul {nr}.")
        grup = agregat.setdefault((nume, url, intentie(termen)), {})
        m = grup.setdefault(termen, _Masurare())
        if masurat:
            try:
                impresii = int(rand["impresii"])
                pozitie = float(rand["pozitie"].replace(",", "."))
                if impresii < 0 or not math.isfinite(pozitie) or pozitie < 1:
                    raise ValueError
            except ValueError as exc:
                raise ValueError(f"Impresii sau poziție nevalide la rândul {nr}.") from exc
            m.impresii += impresii
            m.suma_pozitii += impresii * pozitie

    grupuri = []
    for (nume, url, scop), termeni in agregat.items():
        cuvinte = list(termeni)
        g = Grup(scop, nume, cuvinte, produs=nume, pagina=url)
        if masurat:
            cuvinte.sort(key=lambda c: (-termeni[c].impresii, termeni[c].pozitie or math.inf))
            g.impresii = sum(m.impresii for m in termeni.values())
            if g.impresii:
                g.pozitie = sum(m.suma_pozitii for m in termeni.values()) / g.impresii
        grupuri.append(g)
    if masurat:
        grupuri.sort(key=lambda g: (-(g.impresii or 0), g.pozitie or math.inf))
    return grupuri
