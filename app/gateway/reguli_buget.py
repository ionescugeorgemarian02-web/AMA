"""Nucleul pur al bugetelor pe client (8.5): plafoanele pe prioritate, depășirile, pragul de avertizare,
ferestrele. Fără bază și fără rețea; contoarele persistente și interceptorul sunt în `bugete`.

Regulile (decizii F3.8):
- P0 (termen de client în 24 de ore): nu e atins niciodată de buget; consumul lui se numără oricum.
- P1 (producția programată, cotă garantată): continuă peste buget până la `plafon_p1` × buget (implicit
  1,5); abia peste acest plafon se amână. Motiv: 8.5 spune că P0 și P1 au cotă garantată, dar nu spune cât
  de departe; un client nu trebuie să poată consuma fără limită cota agenției prin livrabile P1.
- P2 și P3: se amână de îndată ce bugetul unei ferestre (zi sau lună) este atins.
Plafoanele sunt pe trei axe (apeluri, tokeni, preț-umbră) și pe două ferestre (zi, lună); `None` = fără
limită pe acea axă. Apelurile se rezervă atomic (un apel = +1, doar sub plafon); tokenii și prețul-umbră
sunt cunoscuți abia după apel, deci se verifică ÎNAINTE (consumul de până acum trebuie să fie sub plafon)
și se adaugă DUPĂ. Depășirea posibilă este mărginită de apelurile aflate în zbor în același timp (fiecare
cu cel mult `max_tokeni`).
"""

import datetime as dt
import math
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.operare.motor import Prioritate


class Fereastra(StrEnum):
    ZI = "zi"
    LUNA = "luna"


class Axa(StrEnum):
    APELURI = "apeluri"
    TOKENI = "tokeni"
    PRET = "pret_umbra"


ETICHETE_AXA = {Axa.APELURI: "apeluri", Axa.TOKENI: "tokeni", Axa.PRET: "preț-umbră"}
ETICHETE_FEREASTRA = {Fereastra.ZI: "pe zi", Fereastra.LUNA: "pe lună"}


@dataclass(frozen=True)
class Valori:
    """Trei numere pe aceeași fereastră. La buget: limita (`None` = fără); la consum: ce s-a folosit."""

    apeluri: int | None = None
    tokeni: int | None = None
    pret_umbra: Decimal | None = None


@dataclass(frozen=True)
class Buget:
    zi: Valori = Valori()
    luna: Valori = Valori()
    prag_avertizare: float = 0.8
    plafon_p1: float = 1.5

    def pe(self, fereastra: Fereastra) -> Valori:
        return self.zi if fereastra is Fereastra.ZI else self.luna


@dataclass(frozen=True)
class Consum:
    apeluri: int = 0
    tokeni: int = 0
    pret_umbra: Decimal = Decimal(0)


def plafon(buget: Valori, prioritate: Prioritate, plafon_p1: float) -> Valori:
    """Cât are voie să consume un apel de prioritatea dată într-o fereastră. P0: nimic nu-l oprește."""
    if prioritate is Prioritate.P0:
        return Valori()
    if prioritate is Prioritate.P1:
        return Valori(
            None if buget.apeluri is None else math.ceil(buget.apeluri * plafon_p1),
            None if buget.tokeni is None else math.ceil(buget.tokeni * plafon_p1),
            None if buget.pret_umbra is None else buget.pret_umbra * Decimal(str(plafon_p1)),
        )
    return buget


def permite(consum: Consum, limita: Valori) -> bool:
    """Oglinda în Python a condiției aplicate atomic în bază (testată împotriva ei): încape încă un apel?"""
    if limita.apeluri is not None and consum.apeluri + 1 > limita.apeluri:
        return False
    if limita.tokeni is not None and consum.tokeni >= limita.tokeni:
        return False
    return not (limita.pret_umbra is not None and consum.pret_umbra >= limita.pret_umbra)


def depasiri(consum: Consum, limita: Valori) -> list[Axa]:
    """Axele pe care un apel nou nu mai încape."""
    ies: list[Axa] = []
    if limita.apeluri is not None and consum.apeluri + 1 > limita.apeluri:
        ies.append(Axa.APELURI)
    if limita.tokeni is not None and consum.tokeni >= limita.tokeni:
        ies.append(Axa.TOKENI)
    if limita.pret_umbra is not None and consum.pret_umbra >= limita.pret_umbra:
        ies.append(Axa.PRET)
    return ies


def raport(consum: Consum, buget: Valori, axa: Axa) -> float | None:
    """Cât din buget s-a folosit pe o axă (1,0 = tot); `None` dacă axa nu are buget. Buget 0 și consum > 0
    = 1,0."""
    folosit: int | Decimal
    limita: int | Decimal | None
    if axa is Axa.APELURI:
        folosit, limita = consum.apeluri, buget.apeluri
    elif axa is Axa.TOKENI:
        folosit, limita = consum.tokeni, buget.tokeni
    else:
        folosit, limita = consum.pret_umbra, buget.pret_umbra
    if limita is None:
        return None
    if limita == 0:
        return 1.0 if folosit > 0 else 0.0
    return float(Decimal(folosit) / Decimal(limita))


def axe_la_prag(consum: Consum, buget: Valori, prag: float) -> list[Axa]:
    """Axele care au atins pragul de avertizare (dar nu neapărat bugetul)."""
    return [a for a in Axa if (r := raport(consum, buget, a)) is not None and r >= prag]


# --- ferestrele


def inceput_fereastra(acum: dt.datetime, fereastra: Fereastra, ora_reset: int = 0) -> dt.datetime:
    acum = acum.astimezone(dt.UTC)
    if fereastra is Fereastra.ZI:
        inceput = acum.replace(hour=ora_reset, minute=0, second=0, microsecond=0)
        return inceput if inceput <= acum else inceput - dt.timedelta(days=1)
    inceput = acum.replace(day=1, hour=ora_reset, minute=0, second=0, microsecond=0)
    if inceput <= acum:
        return inceput
    an, luna = (acum.year - 1, 12) if acum.month == 1 else (acum.year, acum.month - 1)
    return inceput.replace(year=an, month=luna)


def sfarsit_fereastra(acum: dt.datetime, fereastra: Fereastra, ora_reset: int = 0) -> dt.datetime:
    inceput = inceput_fereastra(acum, fereastra, ora_reset)
    if fereastra is Fereastra.ZI:
        return inceput + dt.timedelta(days=1)
    an, luna = (inceput.year + 1, 1) if inceput.month == 12 else (inceput.year, inceput.month + 1)
    return inceput.replace(year=an, month=luna)
