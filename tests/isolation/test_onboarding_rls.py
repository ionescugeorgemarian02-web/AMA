"""F4.4 — sesiunile de interviu și întrebările lor sunt date de client: RLS ENABLE + FORCE, fără amestec între clienți."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.db import ContextDb, sesiune
from app.ids import new_id
from app.onboarding import sesiuni
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]


def test_sesiunile_si_intrebarile_se_vad_doar_la_clientul_lor(date: Date) -> None:
    ctx_a, ctx_b = (
        ContextDb(tenant_id=date.a, user_id=date.user_a),
        ContextDb(tenant_id=date.b, user_id=date.user_b),
    )
    with sesiune(ctx_a) as db:
        sa = sesiuni.deschide(db, tenant_id=date.a, utilizator_id=date.user_a).id
    with sesiune(ctx_b) as db:
        sb = sesiuni.deschide(db, tenant_id=date.b, utilizator_id=date.user_b).id
        assert sesiuni.sesiune_deschisa(db, date.a) is None  # nici cerând explicit clientul A
        with pytest.raises(sesiuni.EroareOnboarding):
            sesiuni.sesiune(db, sa)
        assert {r[0] for r in db.execute(text("SELECT DISTINCT sesiune_id FROM onboarding_intrebari"))} == {
            sb
        }
        # nu se poate scrie pentru alt client
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(
                text("INSERT INTO onboarding_sesiuni (id, tenant_id) VALUES (:i, :t)"),
                {"i": new_id(), "t": date.a},
            )
    with sesiune(ContextDb()) as db:  # fără client, baza nu arată nimic
        assert db.execute(text("SELECT count(*) FROM onboarding_sesiuni")).scalar_one() == 0
    with sesiune(ContextDb(agency=True)) as db:
        assert db.execute(text("SELECT count(*) FROM onboarding_sesiuni")).scalar_one() >= 2


def test_un_client_nu_poate_modifica_raspunsurile_altuia(date: Date) -> None:
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db:
        sa = sesiuni.deschide(db, tenant_id=date.a, utilizator_id=date.user_a).id
    with sesiune(ContextDb(tenant_id=date.b, user_id=date.user_b)) as db:
        n = db.execute(
            text("UPDATE onboarding_intrebari SET raspuns = 'furat' WHERE sesiune_id = :s"), {"s": sa}
        ).rowcount
        assert n == 0
        n = db.execute(
            text("UPDATE onboarding_sesiuni SET stare = 'trimis' WHERE id = :s"), {"s": sa}
        ).rowcount
        assert n == 0


def test_tabelele_onboardingului_au_rls_activ_si_fortat(admin_engine: Engine) -> None:
    with admin_engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname IN ('onboarding_sesiuni', 'onboarding_intrebari', 'onboarding_variante_ton')"
            )
        ).all()
    assert rows and all(r[1] and r[2] for r in rows)
    _ = uuid


def test_variantele_de_ton_se_vad_doar_la_clientul_lor(date: Date) -> None:
    ids = {}
    with sesiune(ContextDb(agency=True)) as db:
        for cheie, tenant in (("a", date.a), ("b", date.b)):
            ids[cheie] = new_id()
            db.execute(
                text(
                    "INSERT INTO onboarding_variante_ton (id, tenant_id, grup_id, nr, continut, prompt) "
                    "VALUES (:i, :t, :g, 1, '{}', 'p@1')"
                ),
                {"i": ids[cheie], "t": tenant, "g": new_id()},
            )
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db:
        vazute = {r[0] for r in db.execute(text("SELECT id FROM onboarding_variante_ton"))}
        assert ids["a"] in vazute and ids["b"] not in vazute
        assert (
            db.execute(
                text("UPDATE onboarding_variante_ton SET ales = true WHERE id = :i"), {"i": ids["b"]}
            ).rowcount
            == 0
        )
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(
                text("DELETE FROM onboarding_variante_ton WHERE id = :i"), {"i": ids["a"]}
            )  # fără DELETE
