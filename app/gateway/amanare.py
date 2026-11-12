"""Amânarea durabilă (8.4, 7.5): un apel care nu se poate face acum nu doarme într-un fir și nu eșuează, ci se
reprogramează prin motor până la resetarea cotei.

Apelantul sincron primește `Amanat(pana_la)`. Un flux durabil își reprogramează munca cu `reprogrameaza`:
același
flux, aceleași identificatori, pus în coadă pentru momentul resetării (jobul stă în baza motorului și
supraviețuiește
repornirilor). Gateway-ul nu reține cererea: fluxul știe să-și refacă promptul din identificatorii pe care
îi are.
"""

import datetime as dt
from collections.abc import Callable
from typing import Any

from app.gateway import ceas
from app.gateway.erori import Amanat
from app.operare import motor
from app.operare.motor import Coada, Prioritate


def cheie_reluare(baza: str, amanat: Amanat) -> str:
    """Cheia de idempotență a reprogramării: aceeași amânare nu dublează jobul, o amânare nouă (alt moment)
    da."""
    return f"{baza}:{int(amanat.pana_la.timestamp())}"


def reprogrameaza(
    amanat: Amanat,
    fluxul: Callable[..., Any],
    *args: Any,
    cheie: str,
    coada: Coada | str = Coada.IO,
    prioritate: Prioritate = Prioritate.P1,
    termen: dt.datetime | None = None,
) -> str:
    """Pune `fluxul(*args)` în coadă pentru momentul `amanat.pana_la`. Întoarce identificatorul jobului.

    `cheie` identifică lucrul de făcut (ex. `livrabil:<id>:scriere`); se completează cu momentul amânării,
    deci
    apelată din nou pentru aceeași amânare (reluarea unui pas) nu creează un al doilea job. Momentul se
    raportează
    la ceasul gateway-ului: diferența până la `pana_la` se aplică ceasului real."""
    la_real = dt.datetime.now(dt.UTC) + (amanat.pana_la - ceas.acum())
    return motor.trimite(
        fluxul,
        *args,
        coada=coada,
        prioritate=prioritate,
        termen=termen,
        cheie=cheie_reluare(cheie, amanat),
        la=la_real,
    )
