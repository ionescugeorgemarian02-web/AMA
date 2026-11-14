"""Cercetarea SEO, prima formă (F7.10, C6): grupuri de cuvinte-cheie pe intenție. Nucleu pur, determinist.

Intenția după reguli [I] (cuvinte-semnal în română): informațională, comercială, tranzacțională, locală.
Grupul = aceeași intenție + același termen-cap (primul cuvânt cu sens). Volumele de căutare cer o sursă
externă (la migrare); până atunci ordinea e cea a listei primite."""

import re
from dataclasses import dataclass, field

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

    @property
    def principal(self) -> str:
        return self.cuvinte[0]


def grupeaza(cuvinte: list[str]) -> list[Grup]:
    grupuri: dict[tuple[str, str], Grup] = {}
    for c in cuvinte:
        c = " ".join(c.split())
        if not c:
            continue
        k = (intentie(c), cap(c))
        grupuri.setdefault(k, Grup(*k)).cuvinte.append(c)
    return list(grupuri.values())
