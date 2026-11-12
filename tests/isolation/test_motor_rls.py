"""F2.7 — izolarea tabelelor motorului: coada de erori pe client, semnalele workerilor la nivel de agenție."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.db import ContextDb, sesiune
from app.ids import new_id
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]

INSERARE_EROARE = (
    "INSERT INTO coada_erori (id, tenant_id, workflow_id, flux, stare_job, eroare_tip, cauza, severitate) "
    "VALUES (:i, :t, :w, 'f', 'esuat', 'Eroare', '0123456789abcdef', 'minor')"
)


@pytest.fixture
def erori(date: Date, admin_engine: Engine) -> dict[str, str]:
    ids = {"a": f"wf-a-{new_id()}", "b": f"wf-b-{new_id()}", "sistem": f"wf-s-{new_id()}"}
    with admin_engine.begin() as c:
        c.execute(text("TRUNCATE coada_erori, worker_semnale, worker_evenimente"))
        for cheie, tenant in (("a", date.a), ("b", date.b), ("sistem", None)):
            c.execute(text(INSERARE_EROARE), {"i": new_id(), "t": tenant, "w": ids[cheie]})
        c.execute(text("INSERT INTO worker_semnale (worker_id, pid) VALUES ('w1', 1)"))
        c.execute(
            text("INSERT INTO worker_evenimente (id, worker_id, tip) VALUES (:i, 'w1', 'pornit')"),
            {"i": new_id()},
        )
    return ids


def vazute(ctx: ContextDb) -> set[str]:
    with sesiune(ctx) as s:
        return {r[0] for r in s.execute(text("SELECT workflow_id FROM coada_erori"))}


def test_clientul_vede_doar_erorile_lui_iar_cele_de_sistem_doar_agentia(
    date: Date, erori: dict[str, str]
) -> None:
    assert vazute(ContextDb(tenant_id=date.a, user_id=date.user_a)) == {erori["a"]}
    assert vazute(ContextDb(tenant_id=date.b, user_id=date.user_b)) == {erori["b"]}
    assert vazute(ContextDb(agency=True)) == set(erori.values())
    assert vazute(ContextDb()) == set(), "fără context nu se vede nimic"


def test_clientul_nu_poate_crea_erori_pe_numele_altuia(date: Date, erori: dict[str, str]) -> None:
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        s.execute(text(INSERARE_EROARE), {"i": new_id(), "t": date.b, "w": "intrus-1"})
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        s.execute(text(INSERARE_EROARE), {"i": new_id(), "t": None, "w": "intrus-2"})


def test_clientul_nu_poate_modifica_erorile_altuia(
    date: Date, erori: dict[str, str], admin_engine: Engine
) -> None:
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        assert (
            s.execute(
                text("UPDATE coada_erori SET severitate = 'critic' WHERE workflow_id = :w"), {"w": erori["b"]}
            ).rowcount
            == 0
        )
        assert (
            s.execute(
                text("UPDATE coada_erori SET severitate = 'major' WHERE workflow_id = :w"), {"w": erori["a"]}
            ).rowcount
            == 1
        )
    with admin_engine.connect() as c:
        assert (
            c.execute(
                text("SELECT severitate FROM coada_erori WHERE workflow_id = :w"), {"w": erori["b"]}
            ).scalar_one()
            == "minor"
        )


@pytest.mark.parametrize("ctx", ["agentie", "client"])
def test_nimic_nu_se_sterge_din_coada_de_erori(date: Date, erori: dict[str, str], ctx: str) -> None:
    context = ContextDb(agency=True) if ctx == "agentie" else ContextDb(tenant_id=date.a, user_id=date.user_a)
    with pytest.raises(DBAPIError, match=r"(?i)permission denied"), sesiune(context) as s:
        s.execute(text("DELETE FROM coada_erori"))


def test_inchiderea_cere_momentul_si_coerenta(date: Date, erori: dict[str, str]) -> None:
    with pytest.raises(DBAPIError), sesiune(ContextDb(agency=True)) as s:
        s.execute(text("UPDATE coada_erori SET stare = 'inchisa' WHERE workflow_id = :w"), {"w": erori["a"]})
    with pytest.raises(DBAPIError), sesiune(ContextDb(agency=True)) as s:
        s.execute(
            text("UPDATE coada_erori SET severitate = 'urgent' WHERE workflow_id = :w"), {"w": erori["a"]}
        )
    with sesiune(ContextDb(agency=True)) as s:
        s.execute(
            text("UPDATE coada_erori SET stare = 'inchisa', inchis_la = now() WHERE workflow_id = :w"),
            {"w": erori["a"]},
        )


@pytest.mark.parametrize("tabel", ["worker_semnale", "worker_evenimente"])
def test_semnalele_workerilor_sunt_invizibile_si_neinscriptibile_pentru_clienti(
    date: Date, erori: dict[str, str], tabel: str
) -> None:
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        assert s.execute(text(f"SELECT count(*) FROM {tabel}")).scalar_one() == 0
    with sesiune(ContextDb(agency=True)) as s:
        assert s.execute(text(f"SELECT count(*) FROM {tabel}")).scalar_one() == 1
    inserare = (
        "INSERT INTO worker_semnale (worker_id, pid) VALUES ('intrus', 2)"
        if tabel == "worker_semnale"
        else "INSERT INTO worker_evenimente (id, worker_id, tip) VALUES (gen_random_uuid(), 'intrus', 'pornit')"
    )
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        s.execute(text(inserare))


def test_evenimentele_workerilor_sunt_doar_adaugari(date: Date, erori: dict[str, str]) -> None:
    for instructiune in ("UPDATE worker_evenimente SET worker_id = 'x'", "DELETE FROM worker_evenimente"):
        with pytest.raises(DBAPIError, match=r"(?i)permission denied"), sesiune(ContextDb(agency=True)) as s:
            s.execute(text(instructiune))
