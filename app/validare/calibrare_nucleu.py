"""Nucleul pur al calibrării judecătorilor (G14, F5.8, docs/09 §9.6): eșantionarea, acordul cu omul și deriva.

Fără bază, fără ceas, fără fișiere. „Pozitiv” înseamnă EȘEC (judecătorul spune că textul are o problemă).

- Eșantionul este determinist: ordinea vine din sha256(sămânță + id), stratificat pe judecător (fiecare
primește cel mult
  `n` verdicte), ca un judecător rar să nu dispară sub unul frecvent.
- Acordul: procentul de etichete „corect”, kappa Cohen între decizia judecătorului și adevărul stabilit de om
(verdictul
  dacă omul spune „corect”, opusul dacă spune „greșit”) și intervalul Wilson de 95% pentru procent.
- Deriva: rata de trecere a unui judecător într-o săptămână față de media săptămânilor anterioare cu ACEEAȘI
versiune
  (validator, treaptă, versiune, prompt, model); o schimbare de versiune nu e derivă.
"""

import hashlib
import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

PRAG_ACORD = 0.85  # docs/09 §9.6 și §9.9: acord judecător–om de cel puțin 85%
MINIM_ETICHETE = 20  # [I] sub atâtea etichete procentul nu se ia drept semnal (nu se alertează)
Z95 = 1.959964
PRAG_DERIVA = 0.20  # [I] diferența absolută a ratei de trecere față de referință
MINIM_DERIVA = 10  # [I] verdicte pe săptămână (și în referință) sub care nu se judecă deriva


def cheie_esantion(saminta: str, ident: str) -> str:
    return hashlib.sha256(f"{saminta}:{ident}".encode()).hexdigest()


def esantioneaza(candidati: Iterable[tuple[str, str]], n: int, saminta: str) -> list[str]:
    """Din perechi (id, judecător) alege cel mult `n` id-uri pe judecător, determinist pentru aceeași
    sămânță."""
    pe_judecator: dict[str, list[str]] = defaultdict(list)
    for ident, judecator in candidati:
        pe_judecator[judecator].append(ident)
    ales: list[str] = []
    for judecator in sorted(pe_judecator):
        ids = sorted(set(pe_judecator[judecator]), key=lambda i: cheie_esantion(saminta, i))
        ales += ids[: max(n, 0)]
    return ales


def wilson(succese: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Intervalul Wilson pentru o proporție; `None` fără observații."""
    if n == 0:
        return None
    p = succese / n
    numitor = 1 + z * z / n
    centru = (p + z * z / (2 * n)) / numitor
    raza = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / numitor
    return round(max(0.0, centru - raza), 4), round(min(1.0, centru + raza), 4)


def kappa(perechi: Sequence[tuple[bool, bool]]) -> float | None:
    """Kappa Cohen între două decizii binare; `None` fără perechi sau când acordul întâmplător e total."""
    n = len(perechi)
    if n == 0:
        return None
    po = sum(1 for a, b in perechi if a == b) / n
    pa = sum(1 for a, _ in perechi if a) / n
    pb = sum(1 for _, b in perechi if b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe >= 1:
        return None
    return round((po - pe) / (1 - pe), 4)


@dataclass(frozen=True)
class Acord:
    etichete: int
    corecte: int
    procent: float | None
    kappa: float | None
    interval: tuple[float, float] | None
    sub_prag: bool  # alertă: procent sub prag cu suficiente etichete

    def json(self) -> dict[str, object]:
        return {
            "etichete": self.etichete,
            "corecte": self.corecte,
            "procent": self.procent,
            "kappa": self.kappa,
            "interval": list(self.interval) if self.interval else None,
            "sub_prag": self.sub_prag,
            "prag": PRAG_ACORD,
            "minim_etichete": MINIM_ETICHETE,
        }


def acord(
    etichete: Iterable[tuple[bool, bool]], *, prag: float = PRAG_ACORD, minim: int = MINIM_ETICHETE
) -> Acord:
    """Din perechi (judecătorul_a_spus_esec, omul_spune_corect)."""
    lista = list(etichete)
    n = len(lista)
    corecte = sum(1 for _, ok in lista if ok)
    perechi = [(esec, esec if ok else not esec) for esec, ok in lista]  # (judecător, adevărul după om)
    procent = None if n == 0 else round(corecte / n, 4)
    sub = procent is not None and n >= minim and procent < prag
    return Acord(n, corecte, procent, kappa(perechi), wilson(corecte, n), sub)


@dataclass(frozen=True)
class Saptamana:
    judecator: str  # „G10@V3”
    versiune: str  # validator_versiune + prompt + model: altă versiune = alt judecător pentru derivă
    saptamana: str  # „2026-W46”
    total: int
    trecute: int


@dataclass(frozen=True)
class Deriva:
    judecator: str
    versiune: str
    saptamana: str
    rata: float
    referinta: float
    diferenta: float

    def json(self) -> dict[str, object]:
        return self.__dict__.copy()


def deriva(
    saptamani: Iterable[Saptamana], *, prag: float = PRAG_DERIVA, minim: int = MINIM_DERIVA
) -> list[Deriva]:
    """Pentru ultima săptămână a fiecărui judecător: alertă dacă rata de trecere s-a mutat cu cel puțin
    `prag` față de
    săptămânile anterioare cu aceeași versiune. Dacă ultima săptămână are altă versiune decât cele de
    dinainte, nu există
    referință (schimbare de prompt / versiune, nu derivă)."""
    pe_judecator: dict[str, list[Saptamana]] = defaultdict(list)
    for s in saptamani:
        pe_judecator[s.judecator].append(s)
    alerte: list[Deriva] = []
    for judecator, lista in sorted(pe_judecator.items()):
        lista.sort(key=lambda s: s.saptamana)
        ultima = lista[-1]
        anterioare = [
            s for s in lista[:-1] if s.versiune == ultima.versiune and s.saptamana != ultima.saptamana
        ]
        total_ref = sum(s.total for s in anterioare)
        if ultima.total < minim or total_ref < minim:
            continue
        rata = ultima.trecute / ultima.total
        referinta = sum(s.trecute for s in anterioare) / total_ref
        if abs(rata - referinta) >= prag:
            alerte.append(
                Deriva(
                    judecator,
                    ultima.versiune,
                    ultima.saptamana,
                    round(rata, 4),
                    round(referinta, 4),
                    round(rata - referinta, 4),
                )
            )
    return alerte
