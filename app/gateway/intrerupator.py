"""Întrerupătorul pe furnizor (8.3, 7.5): erori repetate → furnizorul este scos temporar și reîncercat
după o pauză.
Nucleu pur; starea stă în `gateway_furnizori` (vezi `sanatate`).

Se numără cererile eșuate cu „eroare de server” sau de rețea (nu 429, care are blocajele lui, nici
ieșirile în afara
schemei, care țin de model). La `prag` eșecuri consecutive furnizorul se scoate pentru `pauza`. După
pauză, PRIMA cerere
este o probă: dacă reușește, contorul se golește; dacă eșuează, intrerupătorul se redeschide imediat.
"""

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class StareSanatate:
    erori_consecutive: int = 0
    intrerupt_pana_la: dt.datetime | None = None


def deschis(stare: StareSanatate, acum: dt.datetime) -> bool:
    return stare.intrerupt_pana_la is not None and stare.intrerupt_pana_la > acum


def dupa_esec(stare: StareSanatate, acum: dt.datetime, *, prag: int, pauza_sec: float) -> StareSanatate:
    erori = stare.erori_consecutive + 1
    if erori >= prag:
        return StareSanatate(erori, acum + dt.timedelta(seconds=pauza_sec))
    return StareSanatate(erori, stare.intrerupt_pana_la)


def dupa_succes(_stare: StareSanatate) -> StareSanatate:
    return StareSanatate()
