"""F2.8 — izolarea cererilor de aprobare: un client nu le vede și nu le poate decide pe ale altuia."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.conturi import Rol
from app.db import ContextDb, sesiune
from app.ids import new_id
from app.productie import Hotarare, aprobari
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]

LIVRABIL = (
    "INSERT INTO livrabile (id, tenant_id, tip, canal, buget_apeluri_llm, buget_timp_sec) "
    "VALUES (:i, :t, 'postare', 'facebook', 10, 60)"
)
CERERE = (
    "INSERT INTO aprobari (id, tenant_id, livrabil_id, versiune, clasa_actiune, decident, termen_la, reamintire_la) "
    "VALUES (:i, :t, :l, 1, 'publicare_continut', :d, now() + interval '2 days', now() + interval '1 day')"
)


@pytest.fixture
def cereri(date: Date, admin_engine: Engine) -> dict[str, uuid.UUID]:
    ids = {k: new_id() for k in ("liv_a", "liv_b", "a", "b")}
    with admin_engine.begin() as c:
        for cheie, tenant in (("a", date.a), ("b", date.b)):
            c.execute(text(LIVRABIL), {"i": ids[f"liv_{cheie}"], "t": tenant})
            c.execute(text(CERERE), {"i": ids[cheie], "t": tenant, "l": ids[f"liv_{cheie}"], "d": "operator"})
    return ids


def vazute(ctx: ContextDb) -> set[uuid.UUID]:
    with sesiune(ctx) as s:
        return {r[0] for r in s.execute(text("SELECT id FROM aprobari"))}


def test_clientul_vede_doar_cererile_lui(date: Date, cereri: dict[str, uuid.UUID]) -> None:
    assert cereri["a"] in vazute(ContextDb(tenant_id=date.a, user_id=date.user_a))
    assert cereri["b"] not in vazute(ContextDb(tenant_id=date.a, user_id=date.user_a))
    assert cereri["a"] not in vazute(ContextDb(tenant_id=date.b, user_id=date.user_b))
    assert {cereri["a"], cereri["b"]} <= vazute(ContextDb(agency=True))
    assert vazute(ContextDb()) == set()


def test_clientul_nu_poate_crea_cereri_pe_numele_altuia(date: Date, cereri: dict[str, uuid.UUID]) -> None:
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        s.execute(text(CERERE), {"i": new_id(), "t": date.b, "l": cereri["liv_b"], "d": "client"})
    with pytest.raises(DBAPIError), sesiune(ContextDb()) as s:
        s.execute(text(CERERE), {"i": new_id(), "t": date.a, "l": cereri["liv_a"], "d": "client"})


def test_clientul_nu_poate_modifica_sau_sterge_cererile_altuia(
    date: Date, cereri: dict[str, uuid.UUID], admin_engine: Engine
) -> None:
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        assert (
            s.execute(
                text("UPDATE aprobari SET reamintit_la = now() WHERE id = :i"), {"i": cereri["b"]}
            ).rowcount
            == 0
        )
    with pytest.raises(DBAPIError), sesiune(ContextDb(agency=True)) as s:
        s.execute(text("DELETE FROM aprobari"))
    with admin_engine.connect() as c:
        assert (
            c.execute(
                text("SELECT reamintit_la FROM aprobari WHERE id = :i"), {"i": cereri["b"]}
            ).scalar_one()
            is None
        )


def test_clientul_nu_poate_decide_cererea_altuia_prin_api(date: Date, cereri: dict[str, uuid.UUID]) -> None:
    with (
        pytest.raises(aprobari.AprobareInexistenta),
        sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s,
    ):
        aprobari.decide(s, cereri["b"], Hotarare.APROBAT, utilizator_id=date.user_a, rol=Rol.OPERATOR)
    with pytest.raises(aprobari.AprobareInexistenta), sesiune(ContextDb()) as s:
        aprobari.decide(s, cereri["a"], Hotarare.APROBAT, utilizator_id=date.user_a, rol=Rol.OPERATOR)
