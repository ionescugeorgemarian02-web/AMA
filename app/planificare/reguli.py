"""Nucleul pur al planificatorului de capacitate (A4, tip D): ce încape în ziua de azi și ce se amână.
Fără bază, fără rețea.

Cererea zilei = suma costurilor estimate ale livrabilelor planificate; capacitatea = cererile și tokenii
care mai încap în cotele modelelor din lanțul fiecărui profil, plus minutele de CPU pe culoar greu. Când
cererea depășește capacitatea pe o axă, se amână livrabile până încape:
- ordinea amânării: termenul cel mai îndepărtat întâi (fără termen = cel mai îndepărtat), apoi cel cu id
  mai mare (determinist);
- se amână doar un livrabil al cărui cost atinge o axă depășită (altfel amânarea nu ajută);
- NEATINSE rămân P0 (termen în 24 de ore) și orice livrabil cu termen sub `prag_apropiat`: dacă nu încap,
  planul rămâne peste capacitate și o alertă spune asta (munca lor nu se amână, se vede doar că cota nu
  ajunge).
"""

import datetime as dt
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from app.operare.motor import Prioritate

Axa = tuple[str, str]  # ("apeluri" | "tokeni" | "cpu", profil sau "")


@dataclass(frozen=True)
class Cost:
    # profil -> {"apeluri": n, "tokeni": n}
    profiluri: Mapping[str, Mapping[str, int]] = field(default_factory=dict)
    minute_cpu: float = 0.0

    def pe_axe(self) -> dict[Axa, float]:
        ax: dict[Axa, float] = {}
        for profil, v in self.profiluri.items():
            ax[("apeluri", profil)] = float(v.get("apeluri", 0))
            ax[("tokeni", profil)] = float(v.get("tokeni", 0))
        if self.minute_cpu:
            ax[("cpu", "")] = self.minute_cpu
        return {a: n for a, n in ax.items() if n > 0}


@dataclass(frozen=True)
class Capacitate:
    # profil -> rămas azi (None = fără limită)
    apeluri: Mapping[str, int | None] = field(default_factory=dict)
    tokeni: Mapping[str, int | None] = field(default_factory=dict)
    minute_cpu: float = 0.0

    def limita(self, axa: Axa) -> float | None:
        tip, profil = axa
        if tip == "cpu":
            return self.minute_cpu
        # un profil fără capacitate cunoscută are capacitate 0
        v = (self.apeluri if tip == "apeluri" else self.tokeni).get(profil, 0)
        return None if v is None else float(v)


@dataclass(frozen=True)
class Element:
    id: uuid.UUID
    tenant_id: uuid.UUID
    tip: str
    termen_la: dt.datetime | None
    cost: Cost


class Decizie(StrEnum):
    PASTRAT = "pastrat"
    AMANAT = "amanat"
    PROTEJAT = "protejat"  # termen apropiat sau P0: nu se amână, chiar dacă planul depășește capacitatea


@dataclass(frozen=True)
class Verdict:
    element: Element
    decizie: Decizie
    prioritate: Prioritate
    motiv: str = ""


@dataclass(frozen=True)
class Rezultat:
    verdicte: tuple[Verdict, ...]
    cerere: dict[Axa, float]  # cererea ÎNAINTE de amânări
    ramasa: dict[Axa, float]  # cererea păstrată (inclusiv protejatele)
    depasiri: tuple[Axa, ...]  # axele care au depășit capacitatea înainte de amânări
    peste_capacitate: tuple[Axa, ...]  # axele care rămân depășite și după amânări (din cauza celor protejate)

    def cu_decizia(self, d: Decizie) -> list[Verdict]:
        return [v for v in self.verdicte if v.decizie is d]


def prioritate(termen: dt.datetime | None, acum: dt.datetime) -> Prioritate:
    """P0: termen de client în următoarele 24 de ore (7.5 / 8.5); restul producției programate: P1."""
    return Prioritate.P0 if termen is not None and termen - acum <= dt.timedelta(hours=24) else Prioritate.P1


def protejat(termen: dt.datetime | None, acum: dt.datetime, prag_apropiat: dt.timedelta) -> bool:
    return termen is not None and termen - acum <= prag_apropiat


def _total(elemente: Sequence[Element]) -> dict[Axa, float]:
    t: dict[Axa, float] = {}
    for e in elemente:
        for a, n in e.cost.pe_axe().items():
            t[a] = t.get(a, 0.0) + n
    return t


def _depasite(total: Mapping[Axa, float], cap: Capacitate) -> list[Axa]:
    out = []
    for axa, n in total.items():
        limita = cap.limita(axa)
        if limita is not None and n > limita + 1e-9:
            out.append(axa)
    return sorted(out)


def planifica(
    elemente: Sequence[Element], cap: Capacitate, acum: dt.datetime, *, prag_apropiat: dt.timedelta
) -> Rezultat:
    cerere = _total(elemente)
    depasiri = _depasite(cerere, cap)
    amanate: set[uuid.UUID] = set()
    ramase = list(elemente)
    candidati = [e for e in elemente if not protejat(e.termen_la, acum, prag_apropiat)]
    # cel mai îndepărtat termen întâi; fără termen = infinit

    def cheie(e: Element) -> tuple[bool, float, str]:
        return (e.termen_la is not None, -(e.termen_la.timestamp() if e.termen_la else 0), str(e.id))

    candidati.sort(key=cheie)
    for e in candidati:
        depasite = set(_depasite(_total(ramase), cap))
        if not depasite:
            break
        if depasite & set(e.cost.pe_axe()):
            amanate.add(e.id)
            ramase = [r for r in ramase if r.id != e.id]
    ramasa = _total(ramase)
    peste = tuple(_depasite(ramasa, cap))
    verdicte = []
    for e in elemente:
        pr = prioritate(e.termen_la, acum)
        if e.id in amanate:
            d, motiv = Decizie.AMANAT, "nu încape în cotele zilei; termen îndepărtat"
        elif protejat(e.termen_la, acum, prag_apropiat):
            d, motiv = Decizie.PROTEJAT, "termen apropiat: neatins"
        else:
            d, motiv = Decizie.PASTRAT, ""
        verdicte.append(Verdict(e, d, pr, motiv))
    return Rezultat(tuple(verdicte), cerere, ramasa, tuple(depasiri), peste)
