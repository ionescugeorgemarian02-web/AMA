"""F5.1 — conținutul livrabilului, rulările și verdictele sunt date de client: RLS (ENABLE + FORCE), fără scriere peste
clienți, doar adăugare."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.db import ContextDb, sesiune
from app.ids import new_id
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]
AMPRENTA = "a" * 64


@pytest.fixture
def date_validare(date: Date, admin_engine: Engine) -> dict[str, dict[str, uuid.UUID]]:
    ids: dict[str, dict[str, uuid.UUID]] = {}
    with admin_engine.begin() as c:
        for cheie, tenant in (("a", date.a), ("b", date.b)):
            lid, cid, rid, vid = new_id(), new_id(), new_id(), new_id()
            c.execute(
                text(
                    "INSERT INTO livrabile (id, tenant_id, tip, canal, buget_apeluri_llm, buget_timp_sec) "
                    "VALUES (:i, :t, 'postare', 'facebook', 10, 60)"
                ),
                {"i": lid, "t": tenant},
            )
            c.execute(
                text(
                    "INSERT INTO livrabile_continut (id, tenant_id, livrabil_id, versiune, text, autor, amprenta) "
                    "VALUES (:i, :t, :l, 1, 'Text', 'E4', :a)"
                ),
                {"i": cid, "t": tenant, "l": lid, "a": AMPRENTA},
            )
            c.execute(
                text(
                    "INSERT INTO validari_rulari (id, tenant_id, livrabil_id, versiune, runda, decizie, puncte, prag, amprenta) "
                    "VALUES (:i, :t, :l, 1, 0, 'trece', 0, 4, :a)"
                ),
                {"i": rid, "t": tenant, "l": lid, "a": AMPRENTA},
            )
            c.execute(
                text(
                    "INSERT INTO validari_verdicte (id, tenant_id, rulare_id, livrabil_id, versiune, runda, validator, "
                    "validator_versiune, treapta, rezultat, scor, amprenta) VALUES (:i, :t, :r, :l, 1, 0, 'G1', '1', 'V0', 'trece', 1, :a)"
                ),
                {"i": vid, "t": tenant, "r": rid, "l": lid, "a": AMPRENTA},
            )
            ids[cheie] = {"livrabil": lid, "continut": cid, "rulare": rid, "verdict": vid}
    return ids


TABELE = (
    ("livrabile_continut", "continut"),
    ("validari_rulari", "rulare"),
    ("validari_verdicte", "verdict"),
)


def vazute(ctx: ContextDb, tabel: str) -> set[uuid.UUID]:
    with sesiune(ctx) as s:
        return {r[0] for r in s.execute(text(f"SELECT id FROM {tabel}"))}


@pytest.mark.parametrize(("tabel", "cheie"), TABELE)
def test_fiecare_client_vede_doar_ale_lui(
    date: Date, date_validare: dict[str, dict[str, uuid.UUID]], tabel: str, cheie: str
) -> None:
    a, b = date_validare["a"][cheie], date_validare["b"][cheie]
    ale_a = vazute(ContextDb(tenant_id=date.a, user_id=date.user_a), tabel)
    assert a in ale_a and b not in ale_a
    assert b not in vazute(ContextDb(tenant_id=date.a, user_id=date.user_a), tabel)
    assert {a, b} <= vazute(ContextDb(agency=True), tabel)
    assert vazute(ContextDb(), tabel) == set(), "fără context nu se vede nimic"


@pytest.mark.parametrize("tabel", [t for t, _ in TABELE])
def test_rls_este_activ_si_fortat(admin_engine: Engine, tabel: str) -> None:
    with admin_engine.connect() as c:
        activ, fortat = c.execute(
            text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t"), {"t": tabel}
        ).one()
    assert activ and fortat


def test_un_client_nu_poate_scrie_verdicte_pe_numele_altuia(
    date: Date, date_validare: dict[str, dict[str, uuid.UUID]]
) -> None:
    sql = text(
        "INSERT INTO validari_verdicte (id, tenant_id, rulare_id, livrabil_id, versiune, runda, validator, "
        "validator_versiune, treapta, rezultat, scor, amprenta) "
        "VALUES (:i, :t, :r, :l, 1, 0, 'G1', '1', 'V0', 'trece', 1, :a)"
    )
    valori = {
        "i": new_id(),
        "t": date.b,
        "r": date_validare["b"]["rulare"],
        "l": date_validare["b"]["livrabil"],
        "a": AMPRENTA,
    }
    ctx = ContextDb(tenant_id=date.a, user_id=date.user_a)
    with sesiune(ctx) as db, pytest.raises(DBAPIError), db.begin_nested():
        db.execute(sql, valori)


def test_continutul_nu_se_poate_lega_de_livrabilul_altui_client(
    date: Date, date_validare: dict[str, dict[str, uuid.UUID]]
) -> None:
    sql = text(
        "INSERT INTO livrabile_continut (id, tenant_id, livrabil_id, versiune, text, autor, amprenta) "
        "VALUES (:i, :t, :l, 2, 'furat', 'E4', :a)"
    )
    valori = {"i": new_id(), "t": date.a, "l": date_validare["b"]["livrabil"], "a": AMPRENTA}
    with (
        sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db,
        pytest.raises(DBAPIError),
        db.begin_nested(),
    ):
        db.execute(sql, valori)


@pytest.mark.parametrize("sql", ["UPDATE {t} SET tenant_id = tenant_id", "DELETE FROM {t}"])
@pytest.mark.parametrize("tabel", [t for t, _ in TABELE])
def test_nici_proprietarul_clientului_nu_modifica_si_nu_sterge(
    date: Date, date_validare: dict[str, dict[str, uuid.UUID]], tabel: str, sql: str
) -> None:
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db:
        db.execute(text(sql.format(t=tabel)))


# --- întrebările către client (F5.3) -----------------------------------------------------------------------------------


@pytest.fixture
def intrebari(
    date: Date, date_validare: dict[str, dict[str, uuid.UUID]], admin_engine: Engine
) -> dict[str, uuid.UUID]:
    ids = {}
    with admin_engine.begin() as c:
        for cheie, tenant in (("a", date.a), ("b", date.b)):
            ids[cheie] = new_id()
            c.execute(
                text(
                    "INSERT INTO validari_intrebari (id, tenant_id, livrabil_id, versiune, validator, intrebare) "
                    "VALUES (:i, :t, :l, 1, 'G2', 'Care este prețul abonamentului?')"
                ),
                {"i": ids[cheie], "t": tenant, "l": date_validare[cheie]["livrabil"]},
            )
    return ids


def test_intrebarile_se_vad_doar_la_clientul_lor(date: Date, intrebari: dict[str, uuid.UUID]) -> None:
    ale_a = vazute(ContextDb(tenant_id=date.a, user_id=date.user_a), "validari_intrebari")
    assert intrebari["a"] in ale_a and intrebari["b"] not in ale_a
    assert vazute(ContextDb(), "validari_intrebari") == set()
    assert {intrebari["a"], intrebari["b"]} <= vazute(ContextDb(agency=True), "validari_intrebari")


def test_intrebarea_nu_se_poate_rescrie_doar_starea_ei_se_schimba(
    date: Date, intrebari: dict[str, uuid.UUID]
) -> None:
    ctx = ContextDb(tenant_id=date.a, user_id=date.user_a)
    with sesiune(ctx) as db:
        n = db.execute(
            text(
                "UPDATE validari_intrebari SET stare = 'raspunsa', raspuns = 'da', raspuns_la = now() WHERE id = :i"
            ),
            {"i": intrebari["a"]},
        ).rowcount
        assert n == 1
    with pytest.raises(DBAPIError), sesiune(ctx) as db:
        db.execute(
            text("UPDATE validari_intrebari SET intrebare = 'altceva' WHERE id = :i"), {"i": intrebari["a"]}
        )
    with pytest.raises(DBAPIError), sesiune(ctx) as db:
        db.execute(text("DELETE FROM validari_intrebari WHERE id = :i"), {"i": intrebari["a"]})
    with sesiune(ctx) as db:  # întrebarea altui client nu e vizibilă, deci nici modificabilă
        n = db.execute(
            text("UPDATE validari_intrebari SET stare = 'inchisa', raspuns_la = now() WHERE id = :i"),
            {"i": intrebari["b"]},
        ).rowcount
        assert n == 0


def test_o_intrebare_nu_se_leaga_de_livrabilul_altui_client(
    date: Date, date_validare: dict[str, dict[str, uuid.UUID]]
) -> None:
    with (
        sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db,
        pytest.raises(DBAPIError),
        db.begin_nested(),
    ):
        db.execute(
            text(
                "INSERT INTO validari_intrebari (id, tenant_id, livrabil_id, versiune, validator, intrebare) "
                "VALUES (:i, :t, :l, 1, 'G2', 'Întrebare furată')"
            ),
            {"i": new_id(), "t": date.a, "l": date_validare["b"]["livrabil"]},
        )
