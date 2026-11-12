"""Ajutoare pentru testele producției (F2.3–F2.10): clienți și utilizatori creați direct în bază."""

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text

from app.ids import new_id
from tests.conftest import BazaTest

PAROLA_HASH = "hash-de-proba"  # nu este verificat în aceste teste


@pytest.fixture
def fabrica_clienti(baza: BazaTest, admin_engine: Engine) -> Callable[[], uuid.UUID]:
    def creeaza() -> uuid.UUID:
        cid = new_id()
        with admin_engine.begin() as c:
            c.execute(
                text("INSERT INTO clienti (id, nume) VALUES (:i, :n)"),
                {"i": cid, "n": f"Firma {cid.hex[:6]}"},
            )
        return cid

    return creeaza


@pytest.fixture
def tenant(fabrica_clienti: Callable[[], uuid.UUID]) -> uuid.UUID:
    return fabrica_clienti()


@pytest.fixture
def om(admin_engine: Engine) -> uuid.UUID:
    """Un utilizator (de agenție) pentru deciziile umane."""
    uid = new_id()
    with admin_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO utilizatori (id, email, nume_afisat, parola_hash) VALUES (:i, :e, 'Ana Test', :p)"
            ),
            {"i": uid, "e": f"{uid}@exemplu.test", "p": PAROLA_HASH},
        )
    return uid
