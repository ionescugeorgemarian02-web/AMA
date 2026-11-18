"""FT.3 — indicatorii pe componentă: volum, rate de eșec, cost, durate, coduri; filtrul pe lună și pe client."""

# ruff: noqa: F811
import datetime as dt
import uuid
from decimal import Decimal

import pytest

from app.db import sesiune_agentie, sesiune_tenant
from app.operare import urme
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401

pytestmark = pytest.mark.db
LUNA = dt.datetime(2031, 3, 1, tzinfo=dt.UTC)


def test_indicatorii_pe_componenta(tenant: uuid.UUID) -> None:
    la = LUNA + dt.timedelta(days=3)
    with urme.corelare(tenant_id=tenant):
        for i, rez in enumerate(["ok", "ok", "esec", "amanat"]):
            urme.emite("gateway", "apel:autor", rezultat=rez, cod="" if rez == "ok" else rez,
                       cost=Decimal("0.01"), unitate_cost="usd_umbra", durata_ms=100 * (i + 1), la=la)  # fmt: skip
        urme.emite("validare", "poarta:G2", rezultat="blocat", cod="critic", la=la)
        urme.emite("validare", "poarta:G1", rezultat="ok", la=la)
        urme.emite("motor", "trimis:x", rezultat="info", la=la)
        urme.emite(
            "gateway", "apel:autor", rezultat="esec", la=LUNA - dt.timedelta(seconds=1)
        )  # luna trecută
    with sesiune_agentie() as db:
        ind = {i.componenta: i for i in urme.indicatori.calculeaza(db, LUNA, LUNA + dt.timedelta(days=31))}
    g = ind["gateway"]
    assert g.total == 4 and g.pe_rezultat == {"ok": 2, "esec": 1, "amanat": 1} and g.rata_esec == 0.25
    assert g.cost == {"usd_umbra": Decimal("0.040000")} and g.durata_p50_ms == 250.0
    assert dict(g.coduri) == {"esec": 1, "amanat": 1}
    assert ind["validare"].rata_esec == 0.5 and ind["validare"].coduri == [("critic", 1)]
    assert ind["motor"].rata_esec == 0.0 and ind["motor"].ca_dict()["total"] == 1
    with sesiune_tenant(tenant) as db:  # clientul vede doar ale lui; alt client nu vede nimic
        assert {
            i.componenta for i in urme.indicatori.calculeaza(db, LUNA, LUNA + dt.timedelta(days=31))
        } == set(ind)
    with sesiune_agentie() as db:
        assert (
            urme.indicatori.calculeaza(db, LUNA, LUNA + dt.timedelta(days=31), tenant_id=uuid.uuid4()) == []
        )
