"""F1.7–F1.10 — izolarea tabelelor panoului: abonamentele push sunt pe utilizator, restul la nivel de agenție."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.db import ContextDb, sesiune
from app.ids import new_id
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]

EP_A = "https://push.exemplu.test/" + "a" * 30
EP_B = "https://push.exemplu.test/" + "b" * 30


@pytest.fixture
def abonamente(date: Date, admin_engine: Engine) -> dict[str, object]:
    with admin_engine.begin() as c:
        c.execute(
            text(
                "TRUNCATE abonamente_push, opriri, livrari, cereri_livrare, telegram_actualizari, telegram_confirmari"
            )
        )
        for uid, ep in ((date.user_a, EP_A), (date.user_b, EP_B)):
            c.execute(
                text(
                    "INSERT INTO abonamente_push (id, utilizator_id, endpoint, p256dh, auth) VALUES (:i, :u, :e, 'p', 'a')"
                ),
                {"i": new_id(), "u": uid, "e": ep},
            )
    return {"a": EP_A, "b": EP_B}


def endpoints(s: object) -> set[str]:
    return {r[0] for r in s.execute(text("SELECT endpoint FROM abonamente_push"))}  # type: ignore[attr-defined]


def test_utilizatorul_vede_doar_abonamentele_lui(date: Date, abonamente: dict[str, object]) -> None:
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        assert endpoints(s) == {EP_A}
    with sesiune(ContextDb(tenant_id=date.b, user_id=date.user_b)) as s:
        assert endpoints(s) == {EP_B}


def test_fara_context_nu_se_vede_nimic_si_nu_se_poate_scrie(
    date: Date, abonamente: dict[str, object]
) -> None:
    with sesiune(ContextDb()) as s:
        assert endpoints(s) == set()
    with pytest.raises(DBAPIError), sesiune(ContextDb()) as s:
        s.execute(
            text(
                "INSERT INTO abonamente_push (id, utilizator_id, endpoint, p256dh, auth) VALUES (:i, :u, 'https://x.test/y', 'p', 'a')"
            ),
            {"i": new_id(), "u": date.user_a},
        )


def test_b_nu_poate_sterge_modifica_sau_crea_abonamente_in_numele_lui_a(
    date: Date, abonamente: dict[str, object], admin_engine: Engine
) -> None:
    with sesiune(ContextDb(tenant_id=date.b, user_id=date.user_b)) as s:
        assert s.execute(text("DELETE FROM abonamente_push WHERE endpoint = :e"), {"e": EP_A}).rowcount == 0
        assert (
            s.execute(
                text("UPDATE abonamente_push SET p256dh = 'furat' WHERE endpoint = :e"), {"e": EP_A}
            ).rowcount
            == 0
        )
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.b, user_id=date.user_b)) as s:
        s.execute(
            text(
                "INSERT INTO abonamente_push (id, utilizator_id, endpoint, p256dh, auth) VALUES (:i, :u, 'https://x.test/zz', 'p', 'a')"
            ),
            {"i": new_id(), "u": date.user_a},
        )
    with admin_engine.connect() as c:
        assert (
            c.execute(
                text("SELECT p256dh FROM abonamente_push WHERE endpoint = :e"), {"e": EP_A}
            ).scalar_one()
            == "p"
        )


def test_agentia_citeste_si_sterge_dar_nu_modifica_abonamentele_altora(
    date: Date, abonamente: dict[str, object]
) -> None:
    with sesiune(ContextDb(agency=True, user_id=date.owner_agentie)) as s:
        assert endpoints(s) == {EP_A, EP_B}
        assert s.execute(text("UPDATE abonamente_push SET p256dh = 'x'")).rowcount == 0
        assert s.execute(text("DELETE FROM abonamente_push WHERE endpoint = :e"), {"e": EP_B}).rowcount == 1


def test_opriri_globale_se_vad_peste_tot_cele_pe_client_doar_la_clientul_lui(
    date: Date, abonamente: dict[str, object], admin_engine: Engine
) -> None:
    with admin_engine.begin() as c:
        c.execute(
            text("INSERT INTO opriri (id, tip, activ, canal) VALUES (:i, 'publicare', true, 'panou')"),
            {"i": new_id()},
        )
        for cid in (date.a, date.b):
            c.execute(
                text(
                    "INSERT INTO opriri (id, tip, tenant_id, activ, canal) VALUES (:i, 'client', :t, true, 'panou')"
                ),
                {"i": new_id(), "t": cid},
            )

    def vazute(ctx: ContextDb) -> set[tuple[str, object]]:
        with sesiune(ctx) as s:
            return {(r[0], r[1]) for r in s.execute(text("SELECT tip, tenant_id FROM opriri"))}

    assert vazute(ContextDb(tenant_id=date.a, user_id=date.user_a)) == {
        ("publicare", None),
        ("client", date.a),
    }
    assert vazute(ContextDb(tenant_id=date.b, user_id=date.user_b)) == {
        ("publicare", None),
        ("client", date.b),
    }
    assert len(vazute(ContextDb(agency=True))) == 3
    assert vazute(ContextDb()) == {("publicare", None)}  # fără client: doar steagurile globale


def test_clientii_nu_pot_scrie_opriri_nici_nu_pot_opri_pe_altcineva(
    date: Date, abonamente: dict[str, object]
) -> None:
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        s.execute(
            text("INSERT INTO opriri (id, tip, activ, canal) VALUES (:i, 'publicare', true, 'panou')"),
            {"i": new_id()},
        )
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        s.execute(
            text(
                "INSERT INTO opriri (id, tip, tenant_id, activ, canal) VALUES (:i, 'client', :t, true, 'panou')"
            ),
            {"i": new_id(), "t": date.b},
        )
    with sesiune(ContextDb(agency=True)) as s:
        s.execute(
            text("INSERT INTO opriri (id, tip, activ, canal) VALUES (:i, 'reclame', true, 'panou')"),
            {"i": new_id()},
        )


@pytest.mark.parametrize(
    "tabel", ["livrari", "cereri_livrare", "telegram_actualizari", "telegram_confirmari"]
)
def test_tabelele_de_agentie_sunt_invizibile_si_neinscriptibile_pentru_clienti(
    date: Date, abonamente: dict[str, object], admin_engine: Engine, tabel: str
) -> None:
    sql_inserare = {
        "livrari": "INSERT INTO livrari (id, mediu, cheie, stare, momentul) VALUES (:i, 'staging', 'k', 'reusita', now())",
        "cereri_livrare": "INSERT INTO cereri_livrare (id, tip) VALUES (:i, 'revenire')",
        "telegram_actualizari": "INSERT INTO telegram_actualizari (update_id) VALUES (42)",
        "telegram_confirmari": "INSERT INTO telegram_confirmari (chat_id, cod_hash, tip, expira_la) VALUES (42, decode(repeat('00', 32), 'hex'), 'publicare', now())",
    }[tabel]
    with admin_engine.begin() as c:
        c.execute(text(sql_inserare), {"i": new_id()})
    for ctx in (
        ContextDb(tenant_id=date.a, user_id=date.user_a),
        ContextDb(user_id=date.operator_a),
        ContextDb(),
    ):
        with sesiune(ctx) as s:
            assert s.execute(text(f"SELECT count(*) FROM {tabel}")).scalar_one() == 0
        with pytest.raises(DBAPIError), sesiune(ctx) as s:
            s.execute(text(sql_inserare.replace("42", "43").replace("'k'", "'k2'")), {"i": new_id()})
    with sesiune(ContextDb(agency=True)) as s:
        assert s.execute(text(f"SELECT count(*) FROM {tabel}")).scalar_one() == 1
