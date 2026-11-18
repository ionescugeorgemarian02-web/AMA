"""FT.2 — firul de corelare trece prin motor (job → job), iar componentele lasă urme legate cauzal."""

# ruff: noqa: F811
import uuid

import pytest
from sqlalchemy import Engine, text

from app.operare import motor, urme
from tests.integration import fluxuri_urme
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401

pytestmark = pytest.mark.db


def toate(admin_engine: Engine, fir: str) -> list[dict[str, object]]:
    with admin_engine.begin() as c:
        r = c.execute(text("SELECT * FROM urme WHERE corelare_id = :f ORDER BY la, id"), {"f": fir})
        return [dict(x._mapping) for x in r]


def test_firul_trece_din_cerere_in_job_si_in_jobul_copil(
    admin_engine: Engine, tenant: uuid.UUID, executor: None
) -> None:
    with urme.corelare() as fir, urme.span("http", "POST /proba", tenant_id=tenant) as cerere:
        job = motor.trimite(fluxuri_urme.parinte, str(tenant))
    assert motor.asteapta_flux(job, timeout_sec=60).stare.value == "terminat"
    copil = motor.asteapta_flux(f"urme-copil-{tenant}", timeout_sec=60)
    assert copil.stare.value != "terminat"
    r = toate(admin_engine, fir)
    dupa = {(x["componenta"], x["actiune"]): x for x in r}
    trimis = dupa[("motor", "trimis:proba_urme.parinte")]
    flux_p = dupa[("motor", "flux:proba_urme.parinte")]
    flux_c = dupa[("motor", "flux:proba_urme.copil")]
    assert trimis["cauza_id"] == cerere.id and flux_p["cauza_id"] == trimis["id"]
    assert dupa[("agent", "lucreaza:parinte")]["cauza_id"] == flux_p["id"]
    assert dupa[("motor", "trimis:proba_urme.copil")]["cauza_id"] == flux_p["id"]
    assert flux_c["cauza_id"] == dupa[("motor", "trimis:proba_urme.copil")]["id"]
    assert (flux_c["rezultat"], flux_c["cod"]) == ("esec", "EroareDefinitiva")
    assert {x["tenant_id"] for x in r} == {tenant}


def test_evenimentele_de_domeniu_se_oglindesc(admin_engine: Engine, tenant: uuid.UUID) -> None:
    from app.db import sesiune_tenant
    from app.operare import evenimente

    with urme.corelare() as fir, sesiune_tenant(tenant) as db:
        evenimente.emite(db, "livrabil.tranzitie_refuzata", sursa="productie", date={"motiv": "lipsă brief"})
    (u,) = toate(admin_engine, fir)
    assert (u["componenta"], u["rezultat"], u["motiv"], u["tenant_id"]) == (
        "productie",
        "respins",
        "lipsă brief",
        tenant,
    )


def test_conectorul_http_lasa_urma_cu_status(admin_engine: Engine) -> None:
    import httpx

    from app.connectors.publicare.baza import ClientHttp

    transport = httpx.MockTransport(lambda r: httpx.Response(429 if r.url.path == "/lent" else 200, json={}))
    c = ClientHttp("https://platforma.test", transport=transport)
    with urme.corelare() as fir:
        c.cere("GET", "/ok")
        with pytest.raises((motor.EroareTemporara, motor.EroareDefinitiva)):
            c.cere("GET", "/lent")
    rez = [(x["actiune"], x["rezultat"], x["cod"]) for x in toate(admin_engine, fir)]
    assert rez == [("GET platforma.test/ok", "ok", "200"), ("GET platforma.test/lent", "amanat", "429")]
