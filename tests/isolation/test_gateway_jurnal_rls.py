"""F3.7 — jurnalul de apeluri și conținutul lor sunt date de client: RLS pe `tenant_id`, doar adăugări."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.db import ContextDb, sesiune, sesiune_agentie
from app.ids import new_id
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]

INSERARE_APEL = text(
    "INSERT INTO gateway_apeluri (id, tenant_id, componenta, prioritate, rezultat) VALUES (:i, :t, 'test', 'P2', 'ok')"
)
INSERARE_CONTINUT = text(
    "INSERT INTO gateway_apeluri_continut (apel_id, tenant_id, mesaje, expira_la) "
    "VALUES (:i, :t, '[]'::jsonb, now() + interval '1 day')"
)


@pytest.fixture
def apeluri(date: Date, admin_engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    a, b = new_id(), new_id()
    with admin_engine.begin() as c:
        for i, t in ((a, date.a), (b, date.b)):
            c.execute(INSERARE_APEL, {"i": i, "t": t})
            c.execute(INSERARE_CONTINUT, {"i": i, "t": t})
    return a, b


def test_fiecare_client_isi_vede_doar_apelurile_si_continutul(
    date: Date, apeluri: tuple[uuid.UUID, uuid.UUID]
) -> None:
    a, b = apeluri
    for tabel, coloana in (("gateway_apeluri", "id"), ("gateway_apeluri_continut", "apel_id")):
        interogare = text(f"SELECT {coloana} FROM {tabel} WHERE {coloana} IN (:a, :b)")
        with sesiune(ContextDb(tenant_id=date.a)) as db:
            assert [r[0] for r in db.execute(interogare, {"a": a, "b": b})] == [a]
        with sesiune(ContextDb(tenant_id=date.b)) as db:
            assert [r[0] for r in db.execute(interogare, {"a": a, "b": b})] == [b]
        with sesiune_agentie() as db:
            assert {r[0] for r in db.execute(interogare, {"a": a, "b": b})} == {a, b}
        with sesiune(ContextDb()) as db:  # fără context, baza nu arată nimic
            assert db.execute(interogare, {"a": a, "b": b}).all() == []


def test_un_client_nu_poate_scrie_pe_numele_altuia(date: Date) -> None:
    with pytest.raises((DBAPIError, ProgrammingError)), sesiune(ContextDb(tenant_id=date.a)) as db:
        db.execute(INSERARE_APEL, {"i": new_id(), "t": date.b})
    with sesiune(ContextDb(tenant_id=date.a)) as db:
        db.execute(INSERARE_APEL, {"i": new_id(), "t": date.a})  # pe numele lui, da


def test_jurnalul_este_doar_adaugare_pentru_aplicatie(
    date: Date, apeluri: tuple[uuid.UUID, uuid.UUID]
) -> None:
    a, _ = apeluri
    with pytest.raises((DBAPIError, ProgrammingError)), sesiune(ContextDb(tenant_id=date.a)) as db:
        db.execute(text("UPDATE gateway_apeluri SET rezultat = 'esec' WHERE id = :i"), {"i": a})
    with pytest.raises((DBAPIError, ProgrammingError)), sesiune(ContextDb(tenant_id=date.a)) as db:
        db.execute(text("DELETE FROM gateway_apeluri WHERE id = :i"), {"i": a})
    with pytest.raises((DBAPIError, ProgrammingError)), sesiune(ContextDb(tenant_id=date.a)) as db:
        db.execute(
            text("UPDATE gateway_apeluri_continut SET raspuns = '{}'::jsonb WHERE apel_id = :i"), {"i": a}
        )


def test_stergerea_continutului_expirat_respecta_izolarea(
    date: Date, apeluri: tuple[uuid.UUID, uuid.UUID]
) -> None:
    a, b = apeluri
    with sesiune(ContextDb(tenant_id=date.a)) as db:
        assert (
            db.execute(text("DELETE FROM gateway_apeluri_continut WHERE apel_id = :i"), {"i": b}).rowcount
            == 0
        )
        assert (
            db.execute(text("DELETE FROM gateway_apeluri_continut WHERE apel_id = :i"), {"i": a}).rowcount
            == 1
        )
    with sesiune_agentie() as db:
        assert (
            db.execute(text("DELETE FROM gateway_apeluri_continut WHERE apel_id = :i"), {"i": b}).rowcount
            == 1
        )
        assert (
            db.execute(
                text("SELECT count(*) FROM gateway_apeluri WHERE id IN (:a, :b)"), {"a": a, "b": b}
            ).scalar_one()
            == 2
        )


def test_registrul_de_prompturi_se_citeste_dar_nu_se_scrie_din_context_de_client(date: Date) -> None:
    with sesiune(ContextDb(tenant_id=date.a)) as db:
        db.execute(text("SELECT count(*) FROM gateway_prompturi")).scalar_one()
    with pytest.raises((DBAPIError, ProgrammingError)), sesiune(ContextDb(tenant_id=date.a)) as db:
        db.execute(
            text(
                "INSERT INTO gateway_prompturi (id, nume, versiune, profil, sablon, schema_nume, schema_json, amprenta) "
                "VALUES (:i, 'x.y', 1, 'clasificare', 's', 'm.S', '{}'::jsonb, :h)"
            ),
            {"i": new_id(), "h": "0" * 64},
        )
