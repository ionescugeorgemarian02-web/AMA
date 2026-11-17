# ruff: noqa: F811
"""FT.1 — jurnalul de urme: scriere în tranzacția apelantului și separat, fir și cauză, doar adăugare."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.db import sesiune_agentie, sesiune_tenant
from app.operare import urme
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401

pytestmark = pytest.mark.db


def randuri(admin_engine: Engine, corelare: str) -> list[dict[str, object]]:
    with admin_engine.begin() as c:
        r = c.execute(text("SELECT * FROM urme WHERE corelare_id = :c ORDER BY la, id"), {"c": corelare})
        return [dict(x._mapping) for x in r]


def test_span_imbricat_cu_fir_cauza_cost_si_esec(admin_engine: Engine, tenant: uuid.UUID) -> None:
    intrari = {"email": "ana@exemplu.ro", "token": "t"}
    with urme.corelare(tenant_id=tenant) as fir, urme.span("motor", "flux:proba", intrari=intrari) as parinte:
        with urme.span("gateway", "apel") as s:
            s.cost, s.unitate_cost = 0.0123, "usd_umbra"
        with pytest.raises(ValueError), urme.span("efecte", "trimite"):
            raise ValueError("platforma a refuzat")
    r = {x["componenta"]: x for x in randuri(admin_engine, fir)}
    assert set(r) == {"motor", "gateway", "efecte"}
    assert r["gateway"]["cauza_id"] == r["efecte"]["cauza_id"] == parinte.id == r["motor"]["id"]
    assert r["motor"]["cauza_id"] is None and r["motor"]["tenant_id"] == tenant
    assert (
        float(r["gateway"]["cost"]) == pytest.approx(0.0123) and r["gateway"]["unitate_cost"] == "usd_umbra"
    )
    assert (r["efecte"]["rezultat"], r["efecte"]["cod"]) == ("esec", "ValueError")
    assert r["efecte"]["motiv"] == "platforma a refuzat" and r["efecte"]["durata_ms"] is not None
    assert r["motor"]["intrari"] == {"email": "[email]", "token": "[ascuns]"}


def test_inregistreaza_e_atomic_cu_actiunea_si_nu_o_strica(admin_engine: Engine, tenant: uuid.UUID) -> None:
    with urme.corelare() as fir:
        with pytest.raises(RuntimeError), sesiune_tenant(tenant) as db:
            urme.inregistreaza(db, "aprobare", "respinsa", rezultat="respins", motiv="ton greșit")
            raise RuntimeError("acțiunea a eșuat")
        assert randuri(admin_engine, fir) == []  # anulată odată cu acțiunea
        with sesiune_tenant(tenant) as db:
            assert urme.inregistreaza(db, "x", "y", rezultat="nu-exista") is None  # greșit, dar nu strică
            assert urme.inregistreaza(db, "aprobare", "respinsa", rezultat="respins", motiv="ton") is not None
    assert [x["tenant_id"] for x in randuri(admin_engine, fir)] == [tenant]


def test_rolul_aplicatiei_nu_modifica_si_nu_sterge(tenant: uuid.UUID) -> None:
    with urme.corelare():
        uid = urme.emite("proba", "scrie", tenant_id=tenant)
    assert uid is not None
    for sql in ("UPDATE urme SET motiv = 'x' WHERE id = :i", "DELETE FROM urme WHERE id = :i"):
        with pytest.raises(DBAPIError), sesiune_agentie() as db:
            db.execute(text(sql), {"i": uid})


def test_proprietarul_bazei_e_oprit_de_declansator(admin_engine: Engine, tenant: uuid.UUID) -> None:
    with urme.corelare():
        uid = urme.emite("proba", "scrie", tenant_id=tenant)
    with pytest.raises(DBAPIError), admin_engine.begin() as c:
        c.execute(text("UPDATE urme SET motiv = 'x' WHERE id = :i"), {"i": uid})


def test_oprit_din_configurare(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMA_URME_ACTIVE", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        assert urme.emite("proba", "scrie") is None
    finally:
        monkeypatch.delenv("AMA_URME_ACTIVE")
        get_settings.cache_clear()
