"""F10.1 — izolarea metricilor: un client nu vede și nu scrie citirile altuia."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.db import ContextDb, sesiune
from app.ids import new_id
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]

LIVRABIL = (
    "INSERT INTO livrabile (id, tenant_id, tip, canal, buget_apeluri_llm, buget_timp_sec) "
    "VALUES (:i, :t, 'postare', 'facebook', 10, 60)"
)
METRICI = (
    "INSERT INTO metrici_postari (id, tenant_id, livrabil_id, canal, interval, stare, valori, publicat_la) "
    "VALUES (:i, :t, :l, 'facebook', :n, 'citit', '{\"afisari\": 5}', now())"
)


@pytest.fixture
def metrici(date: Date, admin_engine: Engine) -> dict[str, uuid.UUID]:
    ids = {k: new_id() for k in ("liv_a", "liv_b", "a", "b")}
    with admin_engine.begin() as c:
        for k, tenant in (("a", date.a), ("b", date.b)):
            c.execute(text(LIVRABIL), {"i": ids[f"liv_{k}"], "t": tenant})
            c.execute(text(METRICI), {"i": ids[k], "t": tenant, "l": ids[f"liv_{k}"], "n": "1h"})
    return ids


def vazute(ctx: ContextDb) -> set[object]:
    with sesiune(ctx) as s:
        return {r[0] for r in s.execute(text("SELECT id FROM metrici_postari"))}


def test_clientul_vede_doar_metricile_lui(date: Date, metrici: dict[str, uuid.UUID]) -> None:
    m = metrici
    assert vazute(ContextDb(tenant_id=date.a, user_id=date.user_a)) & {m["a"], m["b"]} == {m["a"]}
    assert vazute(ContextDb(tenant_id=date.b, user_id=date.user_b)) & {m["a"], m["b"]} == {m["b"]}
    assert {m["a"], m["b"]} <= vazute(ContextDb(agency=True))
    assert vazute(ContextDb()) == set(), "fără context, baza nu arată nimic"


def test_clientul_nu_poate_scrie_metrici_pentru_altul(date: Date, metrici: dict[str, uuid.UUID]) -> None:
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        s.execute(text(METRICI), {"i": new_id(), "t": date.b, "l": metrici["liv_b"], "n": "24h"})
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        schimbate = s.execute(
            text("UPDATE metrici_postari SET valori = '{\"afisari\": 999}' WHERE id = :i"),
            {"i": metrici["b"]},
        ).rowcount
    assert schimbate == 0


def test_baza_refuza_cifre_pe_un_rand_ratat(
    date: Date, metrici: dict[str, uuid.UUID], admin_engine: Engine
) -> None:
    with pytest.raises(DBAPIError), admin_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO metrici_postari (id, tenant_id, livrabil_id, canal, interval, stare, valori, publicat_la) "
                "VALUES (:i, :t, :l, 'facebook', '24h', 'ratat', '{\"afisari\": 5}', now())"
            ),
            {"i": new_id(), "t": date.a, "l": metrici["liv_a"]},
        )


def test_curbele_de_retentie_sunt_izolate(
    date: Date, metrici: dict[str, uuid.UUID], admin_engine: Engine
) -> None:
    puncte = "[" + ",".join(f"[{i / 20}, 0.5]" for i in range(1, 21)) + "]"
    sql = (
        "INSERT INTO curbe_retentie (id, tenant_id, livrabil_id, canal, id_extern, interval, puncte) "
        "VALUES (:i, :t, :l, 'youtube', 'vid', '72h', CAST(:p AS jsonb))"
    )
    ids = {"a": new_id(), "b": new_id()}
    with admin_engine.begin() as c:
        for k, tenant in (("a", date.a), ("b", date.b)):
            c.execute(text(sql), {"i": ids[k], "t": tenant, "l": metrici[f"liv_{k}"], "p": puncte})
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        vazute = {r[0] for r in s.execute(text("SELECT id FROM curbe_retentie"))}
    assert vazute & set(ids.values()) == {ids["a"]}
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        s.execute(text(sql), {"i": new_id(), "t": date.b, "l": metrici["liv_b"], "p": puncte})
    with pytest.raises(DBAPIError), admin_engine.begin() as c:  # prea puține puncte: refuzat de bază
        c.execute(text(sql), {"i": new_id(), "t": date.a, "l": metrici["liv_a"], "p": "[[0.5, 0.5]]"})


def test_etichetele_postarilor_sunt_izolate(
    date: Date, metrici: dict[str, uuid.UUID], admin_engine: Engine
) -> None:
    sql = (
        "INSERT INTO etichete_postari (id, tenant_id, livrabil_id, canal, publicat_la, format, zi_saptamana, ora) "
        "VALUES (:i, :t, :l, 'facebook', now(), 'postare', 1, 9)"
    )
    ids = {"a": new_id(), "b": new_id()}
    with admin_engine.begin() as c:
        for k, tenant in (("a", date.a), ("b", date.b)):
            c.execute(text(sql), {"i": ids[k], "t": tenant, "l": metrici[f"liv_{k}"]})
    with sesiune(ContextDb(tenant_id=date.b, user_id=date.user_b)) as s:
        vazute = {r[0] for r in s.execute(text("SELECT id FROM etichete_postari"))}
    assert vazute & set(ids.values()) == {ids["b"]}
    with pytest.raises(DBAPIError), admin_engine.begin() as c:  # recompensă fără tip și interval: refuzată
        c.execute(text("UPDATE etichete_postari SET recompensa = 0.5 WHERE id = :i"), {"i": ids["a"]})
