"""F2.5 — izolarea efectelor externe: un client nu vede, nu cere și nu execută efectele altuia."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.db import ContextDb, sesiune
from app.ids import new_id
from app.operare import efecte
from app.operare.efecte import servicii
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]

LIVRABIL = (
    "INSERT INTO livrabile (id, tenant_id, tip, canal, buget_apeluri_llm, buget_timp_sec) "
    "VALUES (:i, :t, 'postare', 'fals', 10, 60)"
)
EFECT = (
    "INSERT INTO efecte_de_trimis (id, tenant_id, livrabil_id, canal, versiune, tip, cheia) "
    "VALUES (:i, :t, :l, 'fals', 1, 'publicare', :c)"
)


@pytest.fixture
def efecte_de_test(date: Date, admin_engine: Engine) -> dict[str, uuid.UUID]:
    ids = {k: new_id() for k in ("liv_a", "liv_b", "a", "b")}
    with admin_engine.begin() as c:
        for k, tenant in (("a", date.a), ("b", date.b)):
            c.execute(text(LIVRABIL), {"i": ids[f"liv_{k}"], "t": tenant})
            c.execute(text(EFECT), {"i": ids[k], "t": tenant, "l": ids[f"liv_{k}"], "c": f"cheie-{ids[k]}"})
        c.execute(
            text("INSERT INTO conectori_pauze (tenant_id, canal, motiv) VALUES (:t, 'fals', 'x')"),
            {"t": date.b},
        )
    return ids


def vazute(ctx: ContextDb, tabel: str = "efecte_de_trimis") -> set[object]:
    with sesiune(ctx) as s:
        return {
            r[0]
            for r in s.execute(
                text(
                    f"SELECT id FROM {tabel}"
                    if tabel == "efecte_de_trimis"
                    else f"SELECT tenant_id FROM {tabel}"
                )
            )
        }


def test_clientul_vede_doar_efectele_lui(date: Date, efecte_de_test: dict[str, uuid.UUID]) -> None:
    e = efecte_de_test
    assert e["a"] in vazute(ContextDb(tenant_id=date.a, user_id=date.user_a))
    assert e["b"] not in vazute(ContextDb(tenant_id=date.a, user_id=date.user_a))
    assert e["a"] not in vazute(ContextDb(tenant_id=date.b, user_id=date.user_b))
    assert {e["a"], e["b"]} <= vazute(ContextDb(agency=True))
    assert vazute(ContextDb()) == set(), "fără client, baza refuză"


def test_pauzele_conectorilor_sunt_ale_clientului(date: Date, efecte_de_test: dict[str, uuid.UUID]) -> None:
    assert vazute(ContextDb(tenant_id=date.a, user_id=date.user_a), "conectori_pauze") == set()
    assert vazute(ContextDb(tenant_id=date.b, user_id=date.user_b), "conectori_pauze") == {date.b}


def test_clientul_nu_poate_scrie_efecte_pe_numele_altuia(
    date: Date, efecte_de_test: dict[str, uuid.UUID]
) -> None:
    e = efecte_de_test
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        s.execute(text(EFECT), {"i": new_id(), "t": date.b, "l": e["liv_b"], "c": "alta-cheie"})
    with pytest.raises(DBAPIError), sesiune(ContextDb()) as s:
        s.execute(text(EFECT), {"i": new_id(), "t": date.a, "l": e["liv_a"], "c": "alta-cheie-2"})


def test_clientul_nu_poate_modifica_si_nici_sterge_efectele_altuia(
    date: Date, efecte_de_test: dict[str, uuid.UUID]
) -> None:
    e = efecte_de_test
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        assert (
            s.execute(text("UPDATE efecte_de_trimis SET motiv = 'x' WHERE id = :i"), {"i": e["b"]}).rowcount
            == 0
        )
    with pytest.raises(DBAPIError), sesiune(ContextDb(agency=True)) as s:
        s.execute(text("DELETE FROM efecte_de_trimis"))  # nici agenția nu are DELETE


def test_serviciul_ascunde_efectul_altui_client(date: Date, efecte_de_test: dict[str, uuid.UUID]) -> None:
    e = efecte_de_test
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db:
        assert efecte.citeste(db, e["b"]) is None
        with pytest.raises(servicii.EfectInexistent):
            servicii.blocheaza(db, e["b"])
        with pytest.raises(efecte.EfectRefuzat, match="nu există"):
            efecte.cere(
                db, e["liv_b"], porneste=False
            )  # datele clientului B nu se pot folosi din contextul lui A
