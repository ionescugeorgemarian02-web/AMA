"""FT.4 — analiza lunară: regresii față de luna trecută, porți picate, motive de respingere, costuri și lanțul
fiecărui eșec până la evenimentul-sursă; raportul se salvează o dată pe lună (regenerarea îl înlocuiește)."""

# ruff: noqa: F811
import datetime as dt
import uuid

import pytest

from app.db import sesiune_agentie
from app.ids import new_id
from app.operare import motor, urme
from app.operare.urme import analiza, fluxuri
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401

pytestmark = pytest.mark.db
LUNA = dt.date(2032, 5, 1)
LA = dt.datetime(2032, 5, 10, 9, tzinfo=dt.UTC)


def test_raportul_lunar_explica_esecurile(tenant: uuid.UUID) -> None:
    with urme.corelare(tenant_id=tenant):
        for _ in range(10):  # luna trecută: gateway fără eșecuri
            urme.emite(
                "gateway", "apel:autor", la=LA - dt.timedelta(days=30), cost=0.01, unitate_cost="usd_umbra"
            )
        for i in range(10):  # luna asta: 3 eșecuri din 10, cost dublu
            urme.emite("gateway", "apel:autor", la=LA, rezultat="esec" if i < 3 else "ok", cod="timeout" if i < 3 else "",
                       cost=0.02, unitate_cost="usd_umbra")  # fmt: skip
    with urme.corelare(tenant_id=tenant) as fir:
        sursa, flux, conector = new_id(), new_id(), new_id()
        urme.emite("http", "POST /campanii/1/lanseaza", id=sursa, la=LA, actor="utilizator:ana")
        urme.emite("motor", "flux:publicare", id=flux, cauza_id=sursa, la=LA + dt.timedelta(seconds=1),
                   rezultat="esec", cod="EroareDefinitiva")  # fmt: skip
        urme.emite("conector", "POST graph.facebook.com/v23.0/feed", id=conector, cauza_id=flux, rezultat="esec",
                   cod="500", la=LA + dt.timedelta(seconds=2))  # fmt: skip
        urme.emite(
            "validare", "poarta:G2", rezultat="blocat", cod="critic", motiv="afirmație fără sursă", la=LA
        )
        urme.emite("aprobare", "decizie:respins", rezultat="respins", motiv="ton_gresit", la=LA)
        urme.emite("x", "orfan", cauza_id=uuid.uuid4(), rezultat="esec", la=LA)  # părinte pierdut
    with sesiune_agentie() as db:
        r = analiza.genereaza(db, LUNA)
        analiza.genereaza(db, LUNA)  # regenerarea înlocuiește, nu dublează
        assert analiza.luni_cu_raport(db).count(LUNA) == 1 and analiza.raport(db, LUNA) == r
    assert {"componenta": "gateway", "indicator": "rata_esec", "inainte": 0.0, "acum": 0.3} in r["regresii"]
    assert any(x["indicator"] == "cost_usd_umbra" for x in r["regresii"])
    assert r["porti_picate"] == [["validare", "poarta:G2", "critic", 1]]
    assert r["motive_respingere"] == [["aprobare", "decizie:respins", "ton_gresit", 1]]
    assert r["costuri"]["total"]["usd_umbra"] == pytest.approx(0.2)
    assert r["total_esecuri"] == len(r["esecuri"]) == 3 + 2 + 2 + 1 and r["esecuri_netaiate"]
    pe_id = {e["esec"]["id"]: e for e in r["esecuri"]}
    e_flux = pe_id[str(flux)]
    assert e_flux["fir"] == fir and e_flux["sursa"]["id"] == str(sursa)
    assert [x["componenta"] for x in e_flux["lant"]] == ["http", "motor"]
    assert e_flux["cauza_probabila"]["id"] == str(conector)
    assert "cauza: conector/POST graph.facebook.com/v23.0/feed esec 500" in e_flux["explicatie"]
    assert "pornit din http/POST /campanii/1/lanseaza" in e_flux["explicatie"]
    assert [x["componenta"] for x in pe_id[str(conector)]["lant"]] == ["http", "motor", "conector"]
    orfan = next(e for e in r["esecuri"] if e["esec"]["actiune"] == "orfan")
    assert orfan["lant_intrerupt"] and orfan["sursa"]["id"] == str(sursa)  # începutul firului
    assert all(e["sursa"] and e["explicatie"] for e in r["esecuri"])  # fiecare eșec are o sursă


def test_jobul_lunar_e_programat_si_analizeaza_luna_trecuta() -> None:
    fluxuri.declara_programari()
    assert fluxuri.NUME_ANALIZA in {p.nume for p in motor.programari_declarate()}
    assert analiza.luna_precedenta(dt.date(2032, 1, 1)) == dt.date(2031, 12, 1)
    assert analiza.luna_de(dt.datetime(2032, 3, 1, 4, 23, tzinfo=dt.UTC)) == dt.date(2032, 3, 1)
