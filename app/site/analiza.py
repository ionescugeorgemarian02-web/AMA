"""Analiza de trafic proprie (docs/19 §19.1): doar cu acord, fără identificatori, pe serverul nostru.

Fără acord nu se scrie nimic. Cu acord se incrementează un contor pe (zi, pagină): nici IP, nici user-agent,
nici cookie de urmărire."""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import sesiune_agentie
from app.site.modele import Vizita

COOKIE = "ama_consimtamant"
VALORI = ("esential", "analiza")


def acord_analiza(valoare: str | None) -> bool:
    return valoare == "analiza"


def inregistreaza(cale: str, *, zi: dt.date | None = None) -> None:
    zi = zi or dt.datetime.now(dt.UTC).date()
    with sesiune_agentie() as db:
        db.execute(
            pg_insert(Vizita)
            .values(zi=zi, cale=cale[:120], numar=1)
            .on_conflict_do_update(index_elements=["zi", "cale"], set_={"numar": Vizita.numar + 1})
        )


def vizite(zi: dt.date | None = None) -> dict[str, int]:
    zi = zi or dt.datetime.now(dt.UTC).date()
    with sesiune_agentie() as db:
        return dict(db.execute(select(Vizita.cale, Vizita.numar).where(Vizita.zi == zi)).tuples().all())
