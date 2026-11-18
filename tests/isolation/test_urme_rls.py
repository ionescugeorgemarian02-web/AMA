"""FT.1 — izolarea urmelor: clientul își vede doar urmele lui și nu scrie pe numele altuia."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import ContextDb, sesiune
from app.operare import urme
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]


def test_clientul_vede_doar_urmele_lui(date: Date) -> None:
    with urme.corelare():
        a = urme.emite("proba", "a", tenant_id=date.a)
        b = urme.emite("proba", "b", tenant_id=date.b)
        agentie = urme.emite("proba", "agentie")

    def vazute(ctx: ContextDb) -> set[object]:
        with sesiune(ctx) as s:
            return {r[0] for r in s.execute(text("SELECT id FROM urme"))}

    va = vazute(ContextDb(tenant_id=date.a, user_id=date.user_a))
    assert a in va and b not in va and agentie not in va
    assert {a, b, agentie} <= vazute(ContextDb(agency=True))
    assert vazute(ContextDb()) == set()


def test_clientul_nu_scrie_pe_numele_altuia(date: Date) -> None:
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        s.execute(
            text("INSERT INTO urme (id, tenant_id, corelare_id, componenta, actiune, rezultat) "
                 "VALUES (gen_random_uuid(), :t, 'c', 'x', 'y', 'ok')"),
            {"t": date.b},
        )  # fmt: skip
