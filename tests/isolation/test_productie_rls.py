"""F2.3 — izolarea livrabilelor și a istoricului lor: un client nu le vede și nu le poate muta pe ale altuia."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app import productie
from app.db import ContextDb, sesiune
from app.ids import new_id
from app.productie.stari import Stare
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]

INSERARE = (
    "INSERT INTO livrabile (id, tenant_id, tip, canal, buget_apeluri_llm, buget_timp_sec) "
    "VALUES (:i, :t, 'postare', 'facebook', 10, 60)"
)
INSERARE_ISTORIC = (
    "INSERT INTO livrabile_tranzitii (id, tenant_id, livrabil_id, rezultat, din, in_stare, componenta, actor_tip, "
    "versiune) VALUES (:i, :t, :l, 'aplicata', 'planificat', 'briefat', 'x', 'componenta', 1)"
)


@pytest.fixture
def livrabile(date: Date, admin_engine: Engine) -> dict[str, uuid.UUID]:
    ids = {"a": new_id(), "b": new_id()}
    with admin_engine.begin() as c:
        for cheie, tenant in (("a", date.a), ("b", date.b)):
            c.execute(text(INSERARE), {"i": ids[cheie], "t": tenant})
            c.execute(
                text(INSERARE_ISTORIC.replace("'planificat', 'briefat'", "NULL, 'planificat'")),
                {"i": new_id(), "t": tenant, "l": ids[cheie]},
            )
    return ids


def vazute(ctx: ContextDb, tabel: str = "livrabile", coloana: str = "id") -> set[uuid.UUID]:
    with sesiune(ctx) as s:
        return {r[0] for r in s.execute(text(f"SELECT {coloana} FROM {tabel}"))}


def test_clientul_vede_doar_livrabilele_lui(date: Date, livrabile: dict[str, uuid.UUID]) -> None:
    assert livrabile["a"] in vazute(ContextDb(tenant_id=date.a, user_id=date.user_a))
    assert livrabile["b"] not in vazute(ContextDb(tenant_id=date.a, user_id=date.user_a))
    assert livrabile["a"] not in vazute(ContextDb(tenant_id=date.b, user_id=date.user_b))
    assert {livrabile["a"], livrabile["b"]} <= vazute(ContextDb(agency=True))
    assert vazute(ContextDb()) == set(), "fără context nu se vede nimic"


def test_clientul_vede_doar_istoricul_livrabilelor_lui(date: Date, livrabile: dict[str, uuid.UUID]) -> None:
    ale_lui = vazute(ContextDb(tenant_id=date.a, user_id=date.user_a), "livrabile_tranzitii", "livrabil_id")
    assert ale_lui == {livrabile["a"]}
    assert vazute(ContextDb(), "livrabile_tranzitii", "livrabil_id") == set()


def test_clientul_nu_poate_crea_livrabile_pe_numele_altuia(
    date: Date, livrabile: dict[str, uuid.UUID]
) -> None:
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        s.execute(text(INSERARE), {"i": new_id(), "t": date.b})
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        s.execute(text(INSERARE_ISTORIC), {"i": new_id(), "t": date.b, "l": livrabile["b"]})
    with pytest.raises(DBAPIError), sesiune(ContextDb()) as s:
        s.execute(text(INSERARE), {"i": new_id(), "t": date.a})


def test_clientul_nu_poate_modifica_livrabilele_altuia(
    date: Date, livrabile: dict[str, uuid.UUID], admin_engine: Engine
) -> None:
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        assert (
            s.execute(text("UPDATE livrabile SET versiune = 9 WHERE id = :i"), {"i": livrabile["b"]}).rowcount
            == 0
        )
        assert (
            s.execute(text("UPDATE livrabile SET versiune = 2 WHERE id = :i"), {"i": livrabile["a"]}).rowcount
            == 1
        )
    with admin_engine.connect() as c:
        assert (
            c.execute(
                text("SELECT versiune FROM livrabile WHERE id = :i"), {"i": livrabile["b"]}
            ).scalar_one()
            == 1
        )


def test_clientul_nu_poate_muta_livrabilul_altuia_prin_api(
    date: Date, livrabile: dict[str, uuid.UUID]
) -> None:
    with (
        pytest.raises(productie.LivrabilInexistent),
        sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s,
    ):
        productie.muta(s, livrabile["b"], Stare.PLANIFICAT, Stare.BRIEFAT, componenta="test")
    with pytest.raises(productie.LivrabilInexistent), sesiune(ContextDb()) as s:
        productie.muta(s, livrabile["a"], Stare.PLANIFICAT, Stare.BRIEFAT, componenta="test")
    # propriul livrabil se mută
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        assert productie.muta(s, livrabile["a"], Stare.PLANIFICAT, Stare.BRIEFAT, componenta="test").aplicat
    with sesiune(ContextDb(tenant_id=date.b, user_id=date.user_b)) as s:
        assert productie.citeste(s, livrabile["b"]).stare == "planificat"  # type: ignore[union-attr]


def test_nimeni_nu_poate_sterge_livrabile_sau_istoric(date: Date, livrabile: dict[str, uuid.UUID]) -> None:
    for ctx in (ContextDb(tenant_id=date.a, user_id=date.user_a), ContextDb(agency=True)):
        for tabel in ("livrabile", "livrabile_tranzitii"):
            with pytest.raises(DBAPIError), sesiune(ctx) as s:
                s.execute(text(f"DELETE FROM {tabel}"))
