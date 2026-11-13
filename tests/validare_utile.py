"""Ajutoare pentru testele validării (F5): un livrabil adus LEGITIM în `în validare` (toate mutările trec prin
`productie.muta`), cu conținut scris prin `validare.continut.scrie`, plus un registru gol pentru testele cadrului.
# SIMULAT: autorul reparațiilor din teste este scriptat (nu cheamă niciun model)."""

import datetime as dt
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app import productie, validare
from app.db import sesiune_tenant
from app.productie import Stare
from app.validare import registru
from app.validare.autor import ContinutNou, SarcinaReparatie


def livrabil_in_validare(
    tenant: uuid.UUID,
    text: str,
    *,
    campuri: dict[str, Any] | None = None,
    active: list[dict[str, Any]] | None = None,
    tip: str = "postare",
    canal: str = "facebook",
    model_autor: str | None = None,
    autor: str = "E4",
    termen_la: dt.datetime | None = None,
) -> uuid.UUID:
    with sesiune_tenant(tenant) as db:
        lid = productie.creeaza(db, tenant_id=tenant, tip=tip, canal=canal, termen_la=termen_la).id
        parcurs = Stare.PLANIFICAT
        for s in (Stare.BRIEFAT, Stare.IN_SCRIERE):
            productie.muta(db, lid, parcurs, s, componenta="test")
            parcurs = s
        validare.continut.scrie(
            db, lid, text=text, campuri=campuri, active=active, autor=autor, model_autor=model_autor
        )
        productie.muta(db, lid, Stare.IN_SCRIERE, Stare.IN_VALIDARE, componenta=autor)
    return lid


def ruleaza(tenant: uuid.UUID, lid: uuid.UUID, **kw: Any) -> validare.RezultatRunda:
    with sesiune_tenant(tenant) as db:
        return validare.ruleaza_runda(db, lid, **kw)


def verdicte(tenant: uuid.UUID, lid: uuid.UUID, **kw: Any) -> list[validare.VerdictSalvat]:
    with sesiune_tenant(tenant) as db:
        return validare.verdicte(db, lid, **kw)


@pytest.fixture
def registru_gol() -> Iterator[None]:
    """Fără validatorii reali: testele cadrului își înregistrează propriii validatori de probă."""
    with registru.izolat():
        yield


@pytest.fixture
def autor_scriptat() -> Iterator[
    Callable[[Callable[[SarcinaReparatie], ContinutNou]], list[SarcinaReparatie]]
]:
    """Înregistrează un autor de reparații scriptat; întoarce lista sarcinilor primite. La final îl scoate."""
    primite: list[SarcinaReparatie] = []

    def seteaza(f: Callable[[SarcinaReparatie], ContinutNou]) -> list[SarcinaReparatie]:
        def autor(_db: Session, sarcina: SarcinaReparatie) -> ContinutNou:
            primite.append(sarcina)
            return f(sarcina)

        validare.autor.inregistreaza(autor)
        return primite

    yield seteaza
    validare.autor.inregistreaza(None)
