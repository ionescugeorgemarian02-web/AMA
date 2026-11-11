"""Date de izolare: doi clienți cu rânduri proprii, pregătite ca superutilizator (ocolește RLS)."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import Engine, create_engine, text

from app.db.rls import activeaza_rls_tenant
from app.ids import new_id
from tests.conftest import BazaTest

PAROLA_HASH = "hash-de-proba"  # nu este verificat în testele de izolare


@dataclass(frozen=True)
class Date:
    a: uuid.UUID
    b: uuid.UUID
    user_a: uuid.UUID  # client_titular la A
    user_b: uuid.UUID
    owner_agentie: uuid.UUID  # proprietar
    operator_a: uuid.UUID  # operator alocat doar lui A
    sonda_a: uuid.UUID
    sonda_b: uuid.UUID


@pytest.fixture(scope="session")
def sonda(baza: BazaTest) -> Iterator[str]:
    """Un tabel de probă creat exact cum cere AGENTS.md pentru tabele noi: dovedește și ajutorul `rls`."""
    engine = create_engine(baza.owner_url)
    with engine.begin() as c:
        c.execute(
            text(
                "CREATE TABLE sonda_izolare (id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES clienti (id), "
                "valoare text NOT NULL)"
            )
        )
        activeaza_rls_tenant(
            lambda sql: c.execute(text(sql)), "sonda_izolare", drepturi="SELECT, INSERT, UPDATE, DELETE"
        )
    yield "sonda_izolare"
    with engine.begin() as c:
        c.execute(text("DROP TABLE sonda_izolare"))
    engine.dispose()


@pytest.fixture
def date(admin_engine: Engine, sonda: str) -> Date:
    d = Date(*(new_id() for _ in range(8)))
    with admin_engine.begin() as c:
        for cid, nume in ((d.a, "Firma A"), (d.b, "Firma B")):
            c.execute(text("INSERT INTO clienti (id, nume) VALUES (:i, :n)"), {"i": cid, "n": nume})
        for uid, rol, cid in (
            (d.user_a, "client_titular", d.a),
            (d.user_b, "client_titular", d.b),
            (d.owner_agentie, "proprietar", None),
            (d.operator_a, "operator", None),
        ):
            c.execute(
                text(
                    "INSERT INTO utilizatori (id, email, nume_afisat, parola_hash) VALUES (:i, :e, 'x', :p)"
                ),
                {"i": uid, "e": f"{uid}@exemplu.test", "p": PAROLA_HASH},
            )
            c.execute(
                text("INSERT INTO apartenente (id, utilizator_id, tenant_id, rol) VALUES (:i, :u, :t, :r)"),
                {"i": new_id(), "u": uid, "t": cid, "r": rol},
            )
        c.execute(
            text("INSERT INTO alocari (id, utilizator_id, tenant_id) VALUES (:i, :u, :t)"),
            {"i": new_id(), "u": d.operator_a, "t": d.a},
        )
        for sid, cid in ((d.sonda_a, d.a), (d.sonda_b, d.b)):
            c.execute(
                text("INSERT INTO sonda_izolare (id, tenant_id, valoare) VALUES (:i, :t, 'original')"),
                {"i": sid, "t": cid},
            )
    return d
