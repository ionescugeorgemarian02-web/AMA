"""Nucleul pur al bancului de evaluare (K4): matricea de confuzie, precizia, recall-ul, ratele și poarta F5.

Fără bază de date, fără ceas, fără fișiere: primește perechi (așteptat, prezis) și întoarce cifre. „Pozitiv”
înseamnă
EȘEC (defectul pe care validatorul trebuie să-l prindă): recall = ce parte din defecte prinde; rata de
respingere pe
nedrept = ce parte din textele bune sunt oprite.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

CLASE = ("trece", "majora", "critica")  # clasele matricei: trece, eșec major, eșec critic
PRAG_BLOCARE = 0.95  # docs/09 §9.9 și docs/23 poarta F5: cel puțin 95% din materialele greșite sunt blocate
PRAG_RESPINGERE_NEDREAPTA = 0.10  # cel mult 10% din cele bune respinse


def rata(n: int, d: int) -> float | None:
    """n / d, rotunjit la 4 zecimale; `None` când nu există nimic de împărțit (nu 0 și nu 1: nu se
    pretinde)."""
    return None if d == 0 else round(n / d, 4)


@dataclass(frozen=True)
class Confuzie:
    tp: int = 0  # defect prins
    fp: int = 0  # text bun oprit
    fn: int = 0  # defect scăpat
    tn: int = 0  # text bun lăsat să treacă

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def precizie(self) -> float | None:
        return rata(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float | None:
        return rata(self.tp, self.tp + self.fn)

    @property
    def rata_fals_pozitive(self) -> float | None:
        return rata(self.fp, self.fp + self.tn)

    @property
    def acuratete(self) -> float | None:
        return rata(self.tp + self.tn, self.total)

    def json(self) -> dict[str, int | float | None]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "precizie": self.precizie,
            "recall": self.recall,
            "rata_fals_pozitive": self.rata_fals_pozitive,
            "acuratete": self.acuratete,
        }


def clasa(esec: bool, severitate: str | None) -> str:
    """Clasa unui rezultat pentru matrice: `trece`, `majora` sau `critica`."""
    if not esec:
        return "trece"
    return "critica" if severitate == "critica" else "majora"


def confuzie(perechi: Iterable[tuple[bool, bool]]) -> Confuzie:
    """Din perechi (esec_asteptat, esec_prezis)."""
    tp = fp = fn = tn = 0
    for asteptat, prezis in perechi:
        if asteptat and prezis:
            tp += 1
        elif prezis:
            fp += 1
        elif asteptat:
            fn += 1
        else:
            tn += 1
    return Confuzie(tp, fp, fn, tn)


def matrice(perechi: Iterable[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """Matricea de confuzie pe clase: `m[asteptat][prezis]` = numărul de exemple (clasele din `CLASE`)."""
    m = {a: dict.fromkeys(CLASE, 0) for a in CLASE}
    for asteptat, prezis in perechi:
        m[asteptat][prezis] += 1
    return m


def acord_severitate(perechi: Sequence[tuple[str, str]]) -> float | None:
    """Dintre defectele prinse, ce parte au și severitatea așteptată."""
    prinse = [(a, p) for a, p in perechi if a != "trece" and p != "trece"]
    return rata(sum(1 for a, p in prinse if a == p), len(prinse))


@dataclass(frozen=True)
class Poarta:
    rele_total: int
    rele_blocate: int
    bune_total: int
    bune_respinse: int
    rata_blocare: float | None
    rata_respingere: float | None
    trece: bool

    def json(self) -> dict[str, object]:
        return {
            "rele_total": self.rele_total,
            "rele_blocate": self.rele_blocate,
            "bune_total": self.bune_total,
            "bune_respinse": self.bune_respinse,
            "rata_blocare": self.rata_blocare,
            "rata_respingere_pe_nedrept": self.rata_respingere,
            "prag_blocare": PRAG_BLOCARE,
            "prag_respingere_pe_nedrept": PRAG_RESPINGERE_NEDREAPTA,
            "trece": self.trece,
        }


def poarta(rele_total: int, rele_blocate: int, bune_total: int, bune_respinse: int) -> Poarta:
    """Poarta F5. Fără exemple nu trece (un set gol nu dovedește nimic)."""
    rb, rr = rata(rele_blocate, rele_total), rata(bune_respinse, bune_total)
    trece = rb is not None and rr is not None and rb >= PRAG_BLOCARE and rr <= PRAG_RESPINGERE_NEDREAPTA
    return Poarta(rele_total, rele_blocate, bune_total, bune_respinse, rb, rr, trece)
