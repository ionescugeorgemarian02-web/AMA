"""Cascada V0 → V5 (9.1). Nucleu fără bază de date: primește pașii și intrarea.

Reguli:
- pașii rulează în ordinea treptelor (V0 → V4), apoi `ordine`, apoi codul;
- în treptele GRATUITE (V0–V2) rulează toți pașii treptei, ca autorul să primească toate corecturile dintr-o
dată;
  după o treaptă cu eșec cascada se oprește (treptele următoare nu rulează);
- în treptele cu COST (V3, V4) se oprește la primul pas cu eșec: după un blocaj nu se mai consumă cotă;
- un pas care întoarce `None` nu se aplică acestui livrabil și nu produce verdict;
- un validator nu poate întoarce verdictul altui validator (identitatea și versiunea sunt ale lui).
"""

import time
from collections.abc import Sequence
from dataclasses import dataclass, replace

from app.validare.agregare import Agregat, agrega
from app.validare.intrare import Intrare
from app.validare.registru import Pas
from app.validare.verdict import Cost, Treapta, Verdict, VerdictInvalid


class FaraValidatori(RuntimeError):
    """Niciun validator nu se aplică livrabilului: cascada goală ar lăsa totul să treacă, deci e o eroare."""


@dataclass(frozen=True)
class Evaluare:
    verdicte: tuple[Verdict, ...]
    oprit_la: Treapta | None
    agregat: Agregat


def _ca_lista(rezultat: Verdict | Sequence[Verdict] | None) -> list[Verdict]:
    if rezultat is None:
        return []
    if isinstance(rezultat, Verdict):
        return [rezultat]
    return list(rezultat)


def _ruleaza_pas(pas: Pas, intrare: Intrare) -> list[Verdict]:
    start = time.monotonic()
    verdicte = _ca_lista(pas.implementare(intrare))
    durata = int((time.monotonic() - start) * 1000)
    iesire = []
    for v in verdicte:
        if v.validator != pas.definitie.cod or v.versiune != pas.definitie.versiune:
            raise VerdictInvalid(
                f"{pas.definitie.cod}@{pas.definitie.versiune} a întors verdictul {v.validator}@{v.versiune}"
            )
        if v.treapta is not pas.definitie.treapta:
            raise VerdictInvalid(
                f"{pas.definitie.cod}: verdict de treaptă {v.treapta}, pasul e {pas.definitie.treapta}"
            )
        iesire.append(replace(v, cost=v.cost + Cost(durata_ms=durata // max(len(verdicte), 1))))
    return iesire


def ruleaza_pasii(pasi: Sequence[Pas], intrare: Intrare) -> tuple[list[Verdict], Treapta | None]:
    """Verdictele și treapta la care s-a oprit cascada (`None`: a rulat toate treptele aplicabile)."""
    if not pasi:
        raise FaraValidatori(
            f"niciun validator nu se aplică la {intrare.livrabil.tip} / {intrare.livrabil.canal}"
        )
    verdicte: list[Verdict] = []
    trepte = sorted({p.definitie.treapta for p in pasi}, key=lambda t: t.ordine)
    for treapta in trepte:
        blocat = False
        for pas in (p for p in pasi if p.definitie.treapta is treapta):
            nou = _ruleaza_pas(pas, intrare)
            verdicte.extend(nou)
            if any(v.blocheaza for v in nou):
                blocat = True
                if not treapta.gratuita:
                    break
        if blocat:
            return verdicte, treapta
    return verdicte, None


def evalueaza(pasi: Sequence[Pas], intrare: Intrare, *, prag: int) -> Evaluare:
    verdicte, oprit = ruleaza_pasii(pasi, intrare)
    return Evaluare(tuple(verdicte), oprit, agrega(verdicte, prag=prag))
