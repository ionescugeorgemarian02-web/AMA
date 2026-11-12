"""F2.10 — izolarea nivelurilor de autonomie: un client nu le vede și nu le poate schimba pe ale altuia."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.conturi import PermisiuneRefuzata, Rol
from app.db import ContextDb, sesiune
from app.ids import new_id
from app.productie import Clasa, Nivel, autonomie
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]

NIVEL = "INSERT INTO autonomie_niveluri (tenant_id, clasa, nivel) VALUES (:t, 'publicare_continut', 3)"
ISTORIC = (
    "INSERT INTO autonomie_istoric (id, tenant_id, clasa, de_la, la, tip, utilizator_id) "
    "VALUES (:i, :t, 'publicare_continut', 1, 3, 'setare', :u)"
)


@pytest.fixture
def niveluri(date: Date, admin_engine: Engine) -> None:
    with admin_engine.begin() as c:
        c.execute(
            text("DELETE FROM autonomie_niveluri WHERE tenant_id IN (:a, :b)"), {"a": date.a, "b": date.b}
        )
        for tenant in (date.a, date.b):
            c.execute(text(NIVEL), {"t": tenant})
            c.execute(text(ISTORIC), {"i": new_id(), "t": tenant, "u": date.owner_agentie})


def vazute(ctx: ContextDb, tabel: str) -> set[object]:
    with sesiune(ctx) as s:
        return {r[0] for r in s.execute(text(f"SELECT tenant_id FROM {tabel}"))}


@pytest.mark.parametrize("tabel", ["autonomie_niveluri", "autonomie_istoric"])
def test_clientul_vede_doar_nivelurile_lui(date: Date, niveluri: None, tabel: str) -> None:
    assert vazute(ContextDb(tenant_id=date.a, user_id=date.user_a), tabel) == {date.a}
    assert vazute(ContextDb(tenant_id=date.b, user_id=date.user_b), tabel) == {date.b}
    assert {date.a, date.b} <= vazute(ContextDb(agency=True), tabel)
    assert vazute(ContextDb(), tabel) == set()


def test_clientul_nu_poate_scrie_nivelul_altuia(date: Date, niveluri: None) -> None:
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        s.execute(
            text("INSERT INTO autonomie_niveluri (tenant_id, clasa, nivel) VALUES (:t, 'cheltuiala', 4)"),
            {"t": date.b},
        )
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        s.execute(text(ISTORIC), {"i": new_id(), "t": date.b, "u": date.user_a})
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        assert (
            s.execute(
                text("UPDATE autonomie_niveluri SET nivel = 4 WHERE tenant_id = :t"), {"t": date.b}
            ).rowcount
            == 0
        )


def test_nimeni_nu_sterge_niveluri_sau_istoric(date: Date, niveluri: None) -> None:
    for tabel in ("autonomie_niveluri", "autonomie_istoric"):
        for ctx in (ContextDb(tenant_id=date.a, user_id=date.user_a), ContextDb(agency=True)):
            with pytest.raises(DBAPIError), sesiune(ctx) as s:
                s.execute(text(f"DELETE FROM {tabel}"))


def test_nivelul_altui_client_nu_se_schimba_prin_api(date: Date, niveluri: None) -> None:
    """Chiar și proprietarul, dacă lucrează în contextul clientului A, scrie doar în A."""
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.owner_agentie)) as s:
        autonomie.seteaza_nivel(
            s,
            date.b,
            Clasa.CHELTUIALA,
            Nivel.L4,
            utilizator_id=date.owner_agentie,
            rol=Rol.PROPRIETAR,
            motiv="încerc",
        )
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s, pytest.raises(PermisiuneRefuzata):
        autonomie.seteaza_nivel(
            s,
            date.a,
            Clasa.CHELTUIALA,
            Nivel.L4,
            utilizator_id=date.user_a,
            rol=Rol.CLIENT_TITULAR,
            motiv="vreau",
        )
