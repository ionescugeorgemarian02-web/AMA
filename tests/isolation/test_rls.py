"""F1.4 — baza refuză accesul între clienți, nu doar codul aplicației. Rulează ca `ama_app`, pe baza reală."""

import uuid

import psycopg
import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.db import ContextDb, sesiune
from app.ids import new_id
from tests.conftest import BazaTest
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]

TABELE_CU_DATE = ("clienti", "utilizatori", "apartenente", "alocari", "sonda_izolare")


def ids(s: object, sql: str) -> set[object]:
    return {r[0] for r in s.execute(text(sql))}  # type: ignore[attr-defined]


def valoare_admin(admin: Engine, sid: uuid.UUID) -> str:
    with admin.connect() as c:
        return str(c.execute(text("SELECT valoare FROM sonda_izolare WHERE id = :i"), {"i": sid}).scalar_one())


def test_a_nu_citeste_datele_lui_b(date: Date) -> None:
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        assert ids(s, "SELECT id FROM sonda_izolare") == {date.sonda_a}
        assert ids(s, f"SELECT id FROM sonda_izolare WHERE tenant_id = '{date.b}'") == set()
        assert ids(s, f"SELECT id FROM sonda_izolare WHERE id = '{date.sonda_b}'") == set()
        assert ids(s, "SELECT id FROM clienti") == {date.a}
        assert ids(s, "SELECT utilizator_id FROM apartenente") >= {date.user_a}
        assert date.user_b not in ids(s, "SELECT utilizator_id FROM apartenente")
        assert ids(s, "SELECT id FROM alocari WHERE tenant_id <> tenant_id") == set()


def test_a_nu_poate_modifica_datele_lui_b(admin_engine: Engine, date: Date) -> None:
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        r = s.execute(text("UPDATE sonda_izolare SET valoare = 'furat' WHERE id = :i"), {"i": date.sonda_b})
        assert r.rowcount == 0
        r = s.execute(text("UPDATE sonda_izolare SET valoare = 'furat'"))  # toate rândurile vizibile
        assert r.rowcount == 1
    assert valoare_admin(admin_engine, date.sonda_b) == "original"
    assert valoare_admin(admin_engine, date.sonda_a) == "furat"


def test_a_nu_poate_sterge_datele_lui_b(admin_engine: Engine, date: Date) -> None:
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        r = s.execute(text("DELETE FROM sonda_izolare WHERE id = :i"), {"i": date.sonda_b})
        assert r.rowcount == 0
    assert valoare_admin(admin_engine, date.sonda_b) == "original"


def test_a_nu_poate_insera_pentru_b(date: Date) -> None:
    with pytest.raises(DBAPIError, match="row-level security"), sesiune(ContextDb(tenant_id=date.a)) as s:
        s.execute(
            text("INSERT INTO sonda_izolare (id, tenant_id, valoare) VALUES (:i, :t, 'x')"),
            {"i": new_id(), "t": date.b},
        )


def test_a_nu_poate_muta_un_rand_la_b(admin_engine: Engine, date: Date) -> None:
    with pytest.raises(DBAPIError, match="row-level security"), sesiune(ContextDb(tenant_id=date.a)) as s:
        s.execute(text("UPDATE sonda_izolare SET tenant_id = :b WHERE id = :i"), {"b": date.b, "i": date.sonda_a})


def test_a_nu_poate_crea_apartenente_agentie_sau_pentru_b(date: Date) -> None:
    for tenant, rol in ((date.b, "client_vizitator"), (None, "proprietar")):
        with (
            pytest.raises(DBAPIError, match="row-level security"),
            sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s,
        ):
            s.execute(
                text("INSERT INTO apartenente (id, utilizator_id, tenant_id, rol) VALUES (:i, :u, :t, :r)"),
                {"i": new_id(), "u": date.user_a, "t": tenant, "r": rol},
            )


def test_clientul_nu_creeaza_clienti_utilizatori_sau_alocari(date: Date) -> None:
    comenzi = (
        "INSERT INTO clienti (id, nume) VALUES (gen_random_uuid(), 'intrus')",
        "INSERT INTO utilizatori (id, email, nume_afisat, parola_hash) VALUES (gen_random_uuid(), 'i@x.test', 'i', 'h')",
        f"INSERT INTO alocari (id, utilizator_id, tenant_id) VALUES (gen_random_uuid(), '{date.user_a}', '{date.a}')",
    )
    for sql in comenzi:
        with pytest.raises(DBAPIError, match="row-level security"), sesiune(ContextDb(tenant_id=date.a)) as s:
            s.execute(text(sql))


@pytest.mark.parametrize("tabel", TABELE_CU_DATE)
def test_fara_context_zero_randuri(date: Date, tabel: str) -> None:
    with sesiune() as s:
        assert s.execute(text(f"SELECT count(*) FROM {tabel}")).scalar_one() == 0


@pytest.mark.parametrize("tabel", TABELE_CU_DATE)
def test_sql_brut_fara_context_zero_randuri(baza: BazaTest, date: Date, tabel: str) -> None:
    """Conexiune psycopg directă ca `ama_app`, fără să treacă prin `app.db`."""
    dsn = baza.app_url.replace("postgresql+psycopg", "postgresql")
    with psycopg.connect(dsn) as conn:
        assert conn.execute(f"SELECT count(*) FROM {tabel}").fetchone() == (0,)  # type: ignore[arg-type]


@pytest.mark.parametrize("valoare", ["", "nu-este-uuid", "00000000-0000-0000-0000-000000000000", "' OR 1=1 --"])
def test_context_invalid_zero_randuri_fara_erori(date: Date, valoare: str) -> None:
    with sesiune() as s:
        s.execute(text("SELECT set_config('app.tenant_id', :v, true), set_config('app.user_id', :v, true)"), {"v": valoare})
        for tabel in TABELE_CU_DATE:
            assert s.execute(text(f"SELECT count(*) FROM {tabel}")).scalar_one() == 0


def test_fara_context_nu_se_poate_scrie(date: Date) -> None:
    with pytest.raises(DBAPIError, match="row-level security"), sesiune() as s:
        s.execute(
            text("INSERT INTO sonda_izolare (id, tenant_id, valoare) VALUES (:i, :t, 'x')"),
            {"i": new_id(), "t": date.a},
        )


def test_agentia_vede_toti_clientii(date: Date) -> None:
    with sesiune(ContextDb(user_id=date.owner_agentie, agency=True)) as s:
        assert {date.a, date.b} <= ids(s, "SELECT id FROM clienti")
        assert {date.sonda_a, date.sonda_b} <= ids(s, "SELECT id FROM sonda_izolare")


def test_operatorul_vede_doar_clientii_alocati(date: Date) -> None:
    with sesiune(ContextDb(user_id=date.operator_a)) as s:
        assert ids(s, "SELECT id FROM clienti") == {date.a}
        assert ids(s, "SELECT id FROM sonda_izolare") == set()  # datele cer un client activ ales explicit
        assert ids(s, "SELECT tenant_id FROM alocari") == {date.a}
    with sesiune(ContextDb(user_id=date.operator_a, tenant_id=date.a)) as s:
        assert ids(s, "SELECT id FROM sonda_izolare") == {date.sonda_a}


def test_utilizatorul_vede_doar_propriul_rand(date: Date) -> None:
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        assert ids(s, "SELECT id FROM utilizatori") == {date.user_a}
        r = s.execute(text("UPDATE utilizatori SET nume_afisat = 'mutat' WHERE id = :i"), {"i": date.user_b})
        assert r.rowcount == 0


def test_operatorul_nu_isi_poate_adauga_alocari(date: Date) -> None:
    with (
        pytest.raises(DBAPIError, match="row-level security"),
        sesiune(ContextDb(user_id=date.operator_a)) as s,
    ):
        s.execute(
            text("INSERT INTO alocari (id, utilizator_id, tenant_id) VALUES (:i, :u, :t)"),
            {"i": new_id(), "u": date.operator_a, "t": date.b},
        )


def test_drepturile_rolului_aplicatiei_sunt_minime(baza: BazaTest, admin_engine: Engine) -> None:
    with admin_engine.connect() as c:
        def are(tabel: str, drept: str) -> bool:
            return bool(
                c.execute(text("SELECT has_table_privilege('ama_app', :t, :d)"), {"t": tabel, "d": drept}).scalar_one()
            )

        for tabel in ("clienti", "utilizatori", "apartenente"):
            assert not are(tabel, "DELETE")
        for tabel in TABELE_CU_DATE:
            assert not are(tabel, "TRUNCATE")
            assert not are(tabel, "REFERENCES")
            assert not are(tabel, "TRIGGER")
