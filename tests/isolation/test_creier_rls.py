"""F4.1 — Creierul de brand este date de client: RLS pe intrări și versiuni; nivelurile de nișă și platformă
(fără client) le citește orice context autentificat, le scrie doar agenția."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app import creier
from app.creier import Compartiment, Nivel, Sursa, SursaTip
from app.db import ContextDb, sesiune, sesiune_agentie
from app.ids import new_id
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]


def fapt(afirmatie: str) -> dict[str, str]:
    """Conținut valid pentru `registru_fapte` (schema din F4.6: tip, subiect și afirmație atomică)."""
    return {"tip": "altul", "subiect": "Probă de izolare", "afirmatie": afirmatie}


@pytest.fixture
def intrari(date: Date) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    for cheie, tenant, user in (("a", date.a, date.user_a), ("b", date.b, date.user_b)):
        with sesiune(ContextDb(tenant_id=tenant, user_id=user)) as db:
            i, _ = creier.creeaza_intrare(
                db, tenant_id=tenant, compartiment=Compartiment.REGISTRU_FAPTE, continut=fapt(f"Afirmația clientului {cheie}"),
                sursa=Sursa(SursaTip.DECLARATIE_CLIENT), utilizator_id=user,
            )  # fmt: skip
            ids[cheie] = i.id
    with sesiune_agentie(date.owner_agentie) as db:
        i, _ = creier.creeaza_intrare(
            db, tenant_id=None, nivel=Nivel.NISA, compartiment=Compartiment.PLAYBOOK,
            continut={"lectie": f"tipar-{new_id().hex[:6]}"}, sursa=Sursa(SursaTip.AGREGAT),
        )  # fmt: skip
        ids["nisa"] = i.id
    return ids


def vazute(ctx: ContextDb, tabel: str, coloana: str = "id") -> set[uuid.UUID]:
    with sesiune(ctx) as s:
        return {r[0] for r in s.execute(text(f"SELECT {coloana} FROM {tabel}"))}


def test_clientul_vede_doar_intrarile_lui_si_pe_cele_agregate(
    date: Date, intrari: dict[str, uuid.UUID]
) -> None:
    a = ContextDb(tenant_id=date.a, user_id=date.user_a)
    b = ContextDb(tenant_id=date.b, user_id=date.user_b)
    assert intrari["a"] in vazute(a, "creier_intrari") and intrari["b"] not in vazute(a, "creier_intrari")
    assert intrari["b"] in vazute(b, "creier_intrari") and intrari["a"] not in vazute(b, "creier_intrari")
    assert intrari["nisa"] in vazute(a, "creier_intrari") and intrari["nisa"] in vazute(b, "creier_intrari")
    assert {intrari["a"], intrari["b"], intrari["nisa"]} <= vazute(ContextDb(agency=True), "creier_intrari")
    assert vazute(ContextDb(), "creier_intrari") == set()
    versiuni_a = vazute(a, "creier_versiuni", "intrare_id")
    assert intrari["a"] in versiuni_a and intrari["b"] not in versiuni_a
    assert vazute(ContextDb(), "creier_versiuni", "intrare_id") == set()


def test_clientul_nu_poate_scrie_pe_numele_altuia_nici_la_nivel_de_nisa(
    date: Date, intrari: dict[str, uuid.UUID]
) -> None:
    ctx_a = ContextDb(tenant_id=date.a, user_id=date.user_a)
    with pytest.raises(DBAPIError), sesiune(ctx_a) as db:  # intrare pe clientul B
        creier.creeaza_intrare(
            db, tenant_id=date.b, compartiment=Compartiment.REGISTRU_FAPTE, continut=fapt("Afirmație scrisă pe numele altuia"),
            sursa=Sursa(SursaTip.OM), utilizator_id=date.user_a,
        )  # fmt: skip
    with (
        pytest.raises(DBAPIError),
        sesiune(ctx_a) as db,
    ):  # intrare de nișă (fără client) din contextul unui client
        creier.creeaza_intrare(
            db, tenant_id=None, nivel=Nivel.NISA, compartiment=Compartiment.PLAYBOOK, continut={"lectie": "x"},
            sursa=Sursa(SursaTip.AGREGAT),
        )  # fmt: skip
    with sesiune(ctx_a) as db, pytest.raises(creier.IntrareInexistenta):  # versiune nouă la intrarea lui B
        creier.propune_schimbare(
            db,
            intrari["b"],
            continut=fapt("Afirmație furată de la alt client"),
            sursa=Sursa(SursaTip.OM),
            utilizator_id=date.user_a,
        )
    with sesiune(
        ctx_a
    ) as db:  # nici retragerea unei versiuni de nișă: RLS filtrează, niciun rând nu se schimbă
        r = db.execute(
            text(
                "UPDATE creier_versiuni SET stare = 'retras', retras_la = now(), retras_cauza = 'retras' "
                "WHERE intrare_id = :i"
            ),
            {"i": intrari["nisa"]},
        )
        assert r.rowcount == 0  # type: ignore[attr-defined]


def test_o_versiune_nu_poate_purta_alt_client_decat_intrarea(
    date: Date, intrari: dict[str, uuid.UUID], admin_engine: Engine
) -> None:
    with pytest.raises(DBAPIError) as exc, admin_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO creier_versiuni (id, intrare_id, tenant_id, nr, continut, stare, sursa_tip, propus_la) "
                "VALUES (:v, :i, :t, 77, '{}', 'propus', 'sistem', now())"
            ),
            {"v": new_id(), "i": intrari["a"], "t": date.b},
        )
    assert "clientul intrării" in str(exc.value)
