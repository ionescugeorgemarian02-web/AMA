"""F4.7 — pachetele de context sunt date de client: RLS (ENABLE + FORCE), doar adăugări, fără legătură peste clienți."""

import dataclasses
import datetime as dt
import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.creier import pachete
from app.creier.pachete import Element, PachetContext
from app.db import ContextDb, sesiune
from app.ids import new_id
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]
LA = dt.datetime(2026, 5, 1, 12, 0, tzinfo=dt.UTC)


def pachet(
    tenant: uuid.UUID, livrabil_id: uuid.UUID | None = None, text_: str = "Fapt de probă"
) -> PachetContext:
    el = Element("fapte", "fapt", str(new_id()), 1, text_, 5)
    p = PachetContext(
        id=None, tenant_id=tenant, livrabil_id=livrabil_id, tip_sarcina="postare_facebook", canal="facebook",
        intrebare="întrebare de probă", la=LA, buget_tokeni=100, tokeni_folositi=5, depasit=False, elemente=(el,),
        lipsuri=(), taiate=(), amprenta="",
    )  # fmt: skip
    return dataclasses.replace(p, amprenta=pachete.amprenta(pachete.continut_canonic(p)))


def livrabil(admin_engine: Engine, tenant: uuid.UUID) -> uuid.UUID:
    lid = new_id()
    with admin_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO livrabile (id, tenant_id, tip, canal, buget_apeluri_llm, buget_timp_sec) "
                "VALUES (:i, :t, 'postare', 'facebook', 10, 60)"
            ),
            {"i": lid, "t": tenant},
        )
    return lid


def test_fiecare_client_vede_doar_pachetele_lui(date: Date, admin_engine: Engine) -> None:
    ctx_a, ctx_b = (
        ContextDb(tenant_id=date.a, user_id=date.user_a),
        ContextDb(tenant_id=date.b, user_id=date.user_b),
    )
    with sesiune(ctx_a) as db:
        pa = pachete.salveaza(db, pachet(date.a, livrabil(admin_engine, date.a), "al lui A"))
    with sesiune(ctx_b) as db:
        pb = pachete.salveaza(db, pachet(date.b, text_="al lui B"))
    assert pa.id is not None and pb.id is not None
    with sesiune(ctx_a) as db:
        assert pachete.citeste_pachet(db, pa.id) is not None and pachete.citeste_pachet(db, pb.id) is None
        assert pachete.ale_livrabilului(db, pa.livrabil_id or new_id())[0].id == pa.id
    with sesiune(ctx_b) as db:
        assert pachete.citeste_pachet(db, pb.id) is not None and pachete.citeste_pachet(db, pa.id) is None
        assert pa.livrabil_id is not None and pachete.ale_livrabilului(db, pa.livrabil_id) == []
    with sesiune(ContextDb()) as db:  # fără client, baza nu arată nimic
        assert pachete.citeste_pachet(db, pa.id) is None and pachete.citeste_pachet(db, pb.id) is None
    with sesiune(ContextDb(agency=True)) as db:
        assert pachete.citeste_pachet(db, pa.id) is not None and pachete.citeste_pachet(db, pb.id) is not None


def test_un_client_nu_poate_scrie_un_pachet_pe_numele_altuia(date: Date) -> None:
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db:
        pachete.salveaza(db, pachet(date.b))


def test_un_pachet_nu_se_leaga_de_livrabilul_altui_client(date: Date, admin_engine: Engine) -> None:
    al_lui_b = livrabil(admin_engine, date.b)
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db:
        pachete.salveaza(db, pachet(date.a, al_lui_b))
    with (
        pytest.raises(DBAPIError, match="clientul livrabilului"),
        admin_engine.begin() as c,
    ):  # nici ca proprietar al bazei
        c.execute(
            text(
                "INSERT INTO pachete_context (id, tenant_id, livrabil_id, tip_sarcina, intrebare, la, buget_tokeni, "
                "tokeni_folositi, amprenta, continut) VALUES (:i, :t, :l, 'postare', 'x', now(), 10, 1, :a, '{}')"
            ),
            {"i": new_id(), "t": date.a, "l": al_lui_b, "a": "0" * 64},
        )


def test_pachetele_sunt_doar_adaugari(date: Date) -> None:
    ctx_a = ContextDb(tenant_id=date.a, user_id=date.user_a)
    with sesiune(ctx_a) as db:
        p = pachete.salveaza(db, pachet(date.a))
    for sql in (
        "UPDATE pachete_context SET intrebare = 'x' WHERE id = :i",
        "DELETE FROM pachete_context WHERE id = :i",
    ):
        with pytest.raises(ProgrammingError), sesiune(ctx_a) as db:
            db.execute(text(sql), {"i": p.id})


def test_tabelul_are_rls_activat_si_fortat(admin_engine: Engine) -> None:
    with admin_engine.connect() as c:
        rls, fortat = c.execute(
            text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'pachete_context'")
        ).one()
    assert rls and fortat
