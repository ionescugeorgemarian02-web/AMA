"""Poarta FT: o lună simulată (accelerată, ca D-014) prin componentele reale — motor, conector HTTP spre o platformă
SIMULATĂ, producție (evenimente), poarta Creierului — produce un raport care explică fiecare eșec până la sursă."""

# ruff: noqa: F811
import datetime as dt
import uuid

import pytest
from sqlalchemy import Engine, text

from app import creier
from app.creier.compartimente import Compartiment, SursaTip
from app.db import sesiune_agentie, sesiune_tenant
from app.operare import motor, urme
from app.operare.urme import analiza
from tests.integration import fluxuri_poarta_ft as luna_sim
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401

pytestmark = pytest.mark.db
ZILE = 30


def test_o_luna_simulata_cu_fiecare_esec_explicat_pana_la_sursa(
    admin_engine: Engine, tenant: uuid.UUID, om: uuid.UUID, executor: None
) -> None:
    joburi = []
    for z in range(1, ZILE + 1):  # sursa fiecărei zile: planificatorul (o urmă fără cauză)
        with urme.corelare(tenant_id=tenant), urme.span("planificare", f"zi:{z}", tenant_id=tenant):
            joburi.append(motor.trimite(luna_sim.zi, str(tenant), z, cheie=f"poarta-ft-{tenant}-{z}"))
    stari = [motor.asteapta_flux(j, timeout_sec=120).stare.value for j in joburi]
    with (  # brief gol: poarta Creierului îl oprește
        urme.corelare(tenant_id=tenant),
        urme.span("http", "POST /creier/brief/aproba", tenant_id=tenant),
        pytest.raises(creier.PoartaInchisa),
        sesiune_tenant(tenant, om) as db,
    ):
        creier.creeaza_intrare(
            db, tenant_id=tenant, compartiment=Compartiment.BRIEF, cheie="brief-poarta-ft", continut={},
            sursa=creier.Sursa(SursaTip.OM), utilizator_id=om,
        )  # fmt: skip

    with sesiune_agentie() as db:  # raportul lunii, pe clientul simulat (baza de test e comună cu alte teste)
        r = analiza.analizeaza(db, analiza.luna_de(dt.datetime.now(dt.UTC)), tenant_id=tenant)

    zile_500 = [z for z in range(1, ZILE + 1) if z % 9 != 4 and luna_sim.raspuns_platforma(z) == 500]
    zile_rele = [z for z in range(1, ZILE + 1) if z % 9 != 4 and luna_sim.raspuns_platforma(z) != 200]
    assert stari.count("terminat") == ZILE - len(zile_rele) and zile_500
    esecuri = r["esecuri"]
    assert r["client"] == str(tenant) and {e["fir"] for e in esecuri} <= _fire(admin_engine, tenant)
    assert esecuri and r["esecuri_netaiate"] and len(esecuri) == r["total_esecuri"]
    for e in esecuri:  # fiecare eșec: lanț neîntrerupt, de la o sursă fără cauză până la el, și o explicație
        assert not e["lant_intrerupt"], e
        assert e["lant"][0]["id"] == e["sursa"]["id"] and e["lant"][-1]["id"] == e["esec"]["id"]
        assert e["sursa"]["componenta"] in ("planificare", "http")
        assert e["explicatie"].startswith(f"{e['esec']['componenta']}/{e['esec']['actiune']}")
    joburi_cazute = [e for e in esecuri if e["esec"]["actiune"] == "flux:poarta_ft.zi"]
    assert len(joburi_cazute) == len(zile_rele)
    for e in joburi_cazute:  # jobul căzut își arată cauza: platforma
        assert e["cauza_probabila"] and e["cauza_probabila"]["componenta"] == "conector"
        assert e["cauza_probabila"]["cod"] in ("500", "429", "400")
        assert [x["componenta"] for x in e["lant"]] == ["planificare", "motor", "motor"]
        assert "pornit din planificare/zi:" in e["explicatie"]
    refuzuri = [e for e in esecuri if e["esec"]["actiune"] == "livrabil.tranzitie_refuzata"]
    assert len(refuzuri) == sum(1 for z in range(1, ZILE + 1) if z % 9 == 4)
    assert all(e["esec"]["motiv"] == "versiunea nu a trecut validarea" for e in refuzuri)
    assert ["creier", "poarta:brief", "poarta_inchisa", 1] in r["porti_picate"]
    poarta = next(e for e in esecuri if e["esec"]["actiune"] == "poarta:brief")
    assert poarta["sursa"]["actiune"] == "POST /creier/brief/aproba"
    conector = next(i for i in r["indicatori"] if i["componenta"] == "conector")
    assert conector["pe_rezultat"].get("esec", 0) >= len(zile_500)
    assert {"conector", "motor", "planificare", "productie", "creier"} <= {
        p["componenta"] for p in r["prost"]
    } | {i["componenta"] for i in r["indicatori"]}


def _fire(admin_engine: Engine, tenant: uuid.UUID) -> set[str]:
    with admin_engine.begin() as c:
        return {
            x[0]
            for x in c.execute(
                text("SELECT DISTINCT corelare_id FROM urme WHERE tenant_id = :t"), {"t": tenant}
            )
        }
