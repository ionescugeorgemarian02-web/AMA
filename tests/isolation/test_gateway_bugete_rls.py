"""F3.8 — bugetele și consumul unui client sunt date de client: RLS pe `tenant_id`."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.db import ContextDb, sesiune, sesiune_agentie
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]

CONSUM = text(
    "INSERT INTO gateway_consum_client (tenant_id, fereastra, inceput, apeluri) "
    "VALUES (:t, 'zi', '2026-11-12T00:00:00Z', 3)"
)
BUGET = text("INSERT INTO gateway_bugete_client (tenant_id, apeluri_zi) VALUES (:t, 5)")


@pytest.fixture
def randuri(date: Date, admin_engine: Engine) -> None:
    with admin_engine.begin() as c:
        for t in (date.a, date.b):
            c.execute(CONSUM, {"t": t})
            c.execute(BUGET, {"t": t})


def test_fiecare_client_isi_vede_doar_consumul_si_bugetul(date: Date, randuri: None) -> None:
    for tabel in ("gateway_consum_client", "gateway_bugete_client"):
        q = text(f"SELECT tenant_id FROM {tabel} WHERE tenant_id IN (:a, :b)")
        with sesiune(ContextDb(tenant_id=date.a)) as db:
            assert [r[0] for r in db.execute(q, {"a": date.a, "b": date.b})] == [date.a]
        with sesiune(ContextDb(tenant_id=date.b)) as db:
            assert [r[0] for r in db.execute(q, {"a": date.a, "b": date.b})] == [date.b]
        with sesiune_agentie() as db:
            assert {r[0] for r in db.execute(q, {"a": date.a, "b": date.b})} == {date.a, date.b}
        with sesiune(ContextDb()) as db:
            assert db.execute(q, {"a": date.a, "b": date.b}).all() == []


def test_un_client_nu_poate_scrie_consumul_altuia(date: Date, randuri: None) -> None:
    with pytest.raises((DBAPIError, ProgrammingError)), sesiune(ContextDb(tenant_id=date.a)) as db:
        db.execute(
            text(
                "INSERT INTO gateway_consum_client (tenant_id, fereastra, inceput) VALUES (:t, 'luna', now())"
            ),
            {"t": date.b},
        )
    with sesiune(ContextDb(tenant_id=date.a)) as db:  # un UPDATE pe rândul altuia nu atinge nimic
        r = db.execute(
            text("UPDATE gateway_bugete_client SET apeluri_zi = 1 WHERE tenant_id = :t"), {"t": date.b}
        )
        assert r.rowcount == 0
