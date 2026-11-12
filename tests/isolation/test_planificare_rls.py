"""F3.11 — deciziile planificatorului sunt date de client: RLS pe `tenant_id`."""

import datetime as dt

import pytest
from sqlalchemy import Engine, text

from app.db import ContextDb, sesiune, sesiune_agentie
from app.ids import new_id
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]
ZI = dt.date(2030, 1, 15)


@pytest.fixture
def decizii(date: Date, admin_engine: Engine) -> None:
    with admin_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO planificare_planuri (zi, livrabile, pastrate, amanate) VALUES (:z, 2, 1, 1) ON CONFLICT DO NOTHING"
            ),
            {"z": ZI},
        )
        for t in (date.a, date.b):
            c.execute(
                text(
                    "INSERT INTO planificare_decizii (zi, livrabil_id, tenant_id, tip, decizie, prioritate) "
                    "VALUES (:z, :i, :t, 'postare', 'amanat', 'P1')"
                ),
                {"z": ZI, "i": new_id(), "t": t},
            )


def test_fiecare_client_isi_vede_doar_deciziile(date: Date, decizii: None) -> None:
    q = text("SELECT tenant_id FROM planificare_decizii WHERE zi = :z")
    with sesiune(ContextDb(tenant_id=date.a)) as db:
        assert [r[0] for r in db.execute(q, {"z": ZI})] == [date.a]
    with sesiune(ContextDb(tenant_id=date.b)) as db:
        assert [r[0] for r in db.execute(q, {"z": ZI})] == [date.b]
    with sesiune_agentie() as db:
        assert {r[0] for r in db.execute(q, {"z": ZI})} == {date.a, date.b}
    with sesiune(ContextDb()) as db:
        assert db.execute(q, {"z": ZI}).all() == []
