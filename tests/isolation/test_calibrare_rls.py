"""F5.8 — etichetele de calibrare sunt ale clientului verdictului (RLS), iar o etichetă pusă nu se mai
schimbă."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.db import ContextDb, sesiune
from app.ids import new_id
from tests.isolation.conftest import Date
from tests.isolation.test_validare_rls import date_validare as date_validare

pytestmark = [pytest.mark.db, pytest.mark.isolation]
INSERT = text(
    "INSERT INTO calibrare_etichete (id, tenant_id, verdict_id, judecator, versiune, judecator_esec, saptamana) "
    "VALUES (:i, :t, :v, 'G10@V3', '1|p@1|m', true, '2026-W46')"
)


@pytest.fixture
def etichete(
    date: Date,
    date_validare: dict[str, dict[str, uuid.UUID]],
    admin_engine: Engine,
) -> dict[str, uuid.UUID]:
    ids = {}
    with admin_engine.begin() as c:
        for k, t in (("a", date.a), ("b", date.b)):
            ids[k] = new_id()
            c.execute(INSERT, {"i": ids[k], "t": t, "v": date_validare[k]["verdict"]})
    return ids


def test_fiecare_client_vede_doar_etichetele_lui(date: Date, etichete: dict[str, uuid.UUID]) -> None:
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db:
        vazute = {r[0] for r in db.execute(text("SELECT id FROM calibrare_etichete"))}
    assert etichete["a"] in vazute and etichete["b"] not in vazute
    with sesiune(ContextDb()) as db:
        assert db.execute(text("SELECT count(*) FROM calibrare_etichete")).scalar_one() == 0


def test_eticheta_nu_se_leaga_de_verdictul_altui_client(
    date: Date,
    date_validare: dict[str, dict[str, uuid.UUID]],
) -> None:
    with (
        sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db,
        pytest.raises(DBAPIError),
        db.begin_nested(),
    ):
        db.execute(INSERT, {"i": new_id(), "t": date.a, "v": date_validare["b"]["verdict"]})


def test_eticheta_pusa_este_finala(date: Date, etichete: dict[str, uuid.UUID]) -> None:
    ctx = ContextDb(tenant_id=date.a, user_id=date.user_a)
    with sesiune(ctx) as db:
        db.execute(
            text(
                "UPDATE calibrare_etichete SET stare = 'etichetat', eticheta = 'corect', etichetat_la = now() "
                "WHERE id = :i"
            ),
            {"i": etichete["a"]},
        )
    with pytest.raises(DBAPIError), sesiune(ctx) as db:
        db.execute(
            text("UPDATE calibrare_etichete SET eticheta = 'gresit', motiv = 'altceva' WHERE id = :i"),
            {"i": etichete["a"]},
        )
    with pytest.raises(DBAPIError), sesiune(ctx) as db:
        db.execute(text("DELETE FROM calibrare_etichete WHERE id = :i"), {"i": etichete["a"]})
