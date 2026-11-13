"""F5.7 — izolarea bancului: `banc_rulari` doar la nivel de agenție, `exemple_propuse` pe client (RLS, legat
de verdictul
clientului, legătura nu se rescrie), iar restrângerea unei sesiuni de agenție la un client doar îngustează,
apoi se anulează."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.db import ContextDb, ContextNepermis, restrans_la_client, sesiune, sesiune_anulata
from app.ids import new_id
from tests.isolation.conftest import Date
from tests.isolation.test_validare_rls import date_validare as date_validare

pytestmark = [pytest.mark.db, pytest.mark.isolation]

INSERT_EXEMPLU = text(
    "INSERT INTO exemple_propuse (id, tenant_id, validator, sursa, verdict_id, livrabil_id, versiune, tip, canal, text, "
    "asteptat, severitate) VALUES (:i, :t, 'G1', :s, :v, :l, 1, 'postare', 'facebook', 'Text de probă', 'trece', NULL)"
)


@pytest.fixture
def exemple(
    date: Date, date_validare: dict[str, dict[str, uuid.UUID]], admin_engine: Engine
) -> dict[str, uuid.UUID]:
    ids = {}
    with admin_engine.begin() as c:
        for k, t in (("a", date.a), ("b", date.b)):
            ids[k] = new_id()
            v = date_validare[k]
            c.execute(
                INSERT_EXEMPLU,
                {"i": ids[k], "t": t, "s": "contestatie", "v": v["verdict"], "l": v["livrabil"]},
            )
    return ids


def _vazute(ctx: ContextDb, tabel: str) -> set[uuid.UUID]:
    with sesiune(ctx) as s:
        return {r[0] for r in s.execute(text(f"SELECT id FROM {tabel}"))}


def test_exemplele_propuse_se_vad_doar_la_clientul_lor(date: Date, exemple: dict[str, uuid.UUID]) -> None:
    ale_a = _vazute(ContextDb(tenant_id=date.a, user_id=date.user_a), "exemple_propuse")
    assert exemple["a"] in ale_a and exemple["b"] not in ale_a
    assert _vazute(ContextDb(), "exemple_propuse") == set()
    assert {exemple["a"], exemple["b"]} <= _vazute(ContextDb(agency=True), "exemple_propuse")


def test_un_exemplu_nu_se_leaga_de_verdictul_altui_client(
    date: Date,
    date_validare: dict[str, dict[str, uuid.UUID]],
) -> None:
    v = date_validare["b"]
    with (
        sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db,
        pytest.raises(DBAPIError),
        db.begin_nested(),
    ):
        db.execute(
            INSERT_EXEMPLU,
            {"i": new_id(), "t": date.a, "s": "eticheta", "v": v["verdict"], "l": v["livrabil"]},
        )


def test_legatura_exemplului_nu_se_rescrie_si_decizia_e_finala(
    date: Date, exemple: dict[str, uuid.UUID]
) -> None:
    ctx = ContextDb(agency=True, user_id=date.owner_agentie)
    with pytest.raises(DBAPIError), sesiune(ctx) as db:
        db.execute(text("UPDATE exemple_propuse SET validator = 'G2' WHERE id = :i"), {"i": exemple["a"]})
    with sesiune(ctx) as db:
        db.execute(
            text("UPDATE exemple_propuse SET stare = 'respins', decis_la = now() WHERE id = :i"),
            {"i": exemple["a"]},
        )
    with pytest.raises(DBAPIError), sesiune(ctx) as db:
        db.execute(text("UPDATE exemple_propuse SET stare = 'promovat' WHERE id = :i"), {"i": exemple["a"]})
    with pytest.raises(DBAPIError), sesiune(ctx) as db:
        db.execute(text("DELETE FROM exemple_propuse WHERE id = :i"), {"i": exemple["b"]})


def test_rularile_bancului_sunt_doar_ale_agentiei(date: Date, admin_engine: Engine) -> None:
    rid = new_id()
    with admin_engine.begin() as c:
        c.execute(text("INSERT INTO banc_rulari (id) VALUES (:i)"), {"i": rid})
    assert rid in _vazute(ContextDb(agency=True), "banc_rulari")
    assert rid not in _vazute(ContextDb(tenant_id=date.a, user_id=date.user_a), "banc_rulari")
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db:
        db.execute(text("INSERT INTO banc_rulari (id) VALUES (:i)"), {"i": new_id()})


def test_restrangerea_la_client_doar_ingusteaza_si_se_anuleaza(date: Date) -> None:
    with sesiune_anulata(ContextDb(agency=True, user_id=date.owner_agentie)) as db:
        assert {date.a, date.b} <= {r[0] for r in db.execute(text("SELECT id FROM clienti"))}
        with restrans_la_client(db, date.a):
            assert {r[0] for r in db.execute(text("SELECT id FROM clienti"))} == {date.a}
            assert (
                db.execute(
                    text("SELECT count(*) FROM sonda_izolare WHERE tenant_id = :b"), {"b": date.b}
                ).scalar_one()
                == 0
            )
            db.execute(
                text("INSERT INTO sonda_izolare (id, tenant_id, valoare) VALUES (:i, :t, 'x')"),
                {"i": new_id(), "t": date.a},
            )
            with pytest.raises(DBAPIError), db.begin_nested():  # în interior nu se scrie la alt client
                db.execute(
                    text("INSERT INTO sonda_izolare (id, tenant_id, valoare) VALUES (:i, :t, 'x')"),
                    {"i": new_id(), "t": date.b},
                )
        # după ieșire: scopul de agenție revine, iar ce s-a scris înăuntru a dispărut
        assert {date.a, date.b} <= {r[0] for r in db.execute(text("SELECT id FROM clienti"))}
        assert db.execute(text("SELECT count(*) FROM sonda_izolare WHERE valoare = 'x'")).scalar_one() == 0
    with (
        sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db,
        pytest.raises(ContextNepermis),
        restrans_la_client(db, date.b),
    ):
        pass
