"""F4.11 — ecranul „Campanii”: lista strategiilor pe client, detaliul, aprobă / respinge cu motiv, cu CSRF, permisiuni și audit.
„Gata când”: strategia aprobată, cu toate elementele, este vizibilă pe ecranul Campanii (brand de probă, model FALS)."""

# ruff: noqa: F811
import time
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app import creier
from app.conturi import Rol
from app.creier.compartimente import Compartiment, SursaTip
from app.db import sesiune_tenant
from app.onboarding import strategie
from tests.integration.conftest import Cont
from tests.integration.lant_onboarding import pana_la_insight
from tests.integration.test_onboarding_strategie import model_strategie, strategie_valida
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401

pytestmark = pytest.mark.db
Fabrica = Callable[..., Cont]
ELEMENTE = (
    "Ipoteza",
    "Plan pe 30 de zile",
    "Plan pe 90 de zile",
    "Indicator principal",
    "Prag minim",
    "Fereastra de măsurare",
    "Criteriul de oprire",
)


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


def post(client: TestClient, cale: str, **date: str) -> Any:
    return client.post(cale, data={**date, "csrf_token": csrf(client)}, follow_redirects=False)


def propusa(tenant: uuid.UUID, om: uuid.UUID, continut: dict[str, Any] | None = None) -> uuid.UUID:
    with sesiune_tenant(tenant, om) as db:
        i = creier.gaseste_intrare(
            db, tenant_id=tenant, compartiment=Compartiment.STRATEGIE, cheie=strategie.CHEIE_STRATEGIE
        )
        c = continut or strategie_valida()
        if i is None:
            i, _ = creier.creeaza_intrare(db, tenant_id=tenant, compartiment=Compartiment.STRATEGIE, cheie=strategie.CHEIE_STRATEGIE,
                                          continut=c, sursa=creier.Sursa(SursaTip.SISTEM))  # fmt: skip
        else:
            creier.propune_schimbare(db, i.id, continut=c, sursa=creier.Sursa(SursaTip.SISTEM))
        return i.id


def audit(admin: Engine, actiune: str, intrare: uuid.UUID) -> list[dict[str, Any]]:
    with admin.connect() as c:
        return [
            dict(r._mapping)
            for r in c.execute(
                text(
                    "SELECT utilizator_id, tenant_id, detalii FROM jurnal_audit WHERE actiune = :a AND detalii->>'intrare' = :i"
                ),
                {"a": actiune, "i": str(intrare)},
            )
        ]


def test_lista_arata_starea_strategiei_pe_client_si_detaliul_toate_elementele(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    assert (
        "fără strategie" in client.get("/campanii").text and 'href="/campanii"' in client.get("/meniu").text
    )
    assert "Nicio strategie încă" in client.get(f"/campanii/{tenant}").text
    iid = propusa(tenant, om)
    assert "în așteptare" in client.get("/campanii").text
    pagina = client.get(f"/campanii/{tenant}").text
    for element in ELEMENTE:
        assert element in pagina, element
    assert "Propunere în așteptare" in pagina and "Abonamente lunare noi" in pagina and "<table" not in pagina
    assert (
        client.post(f"/campanii/{tenant}/{iid}/aproba", data={"versiune": "1"}).status_code == 403
    )  # fără CSRF
    r = post(client, f"/campanii/{tenant}/{iid}/aproba", versiune="1")
    assert r.status_code == 303 and r.headers["location"] == f"/campanii/{tenant}?mesaj=aprobata"
    assert "aprobată" in client.get("/campanii").text
    pagina = client.get(f"/campanii/{tenant}?mesaj=aprobata").text
    assert "Strategia aprobată" in pagina and "Strategia a fost aprobată" in pagina
    for element in ELEMENTE:
        assert element in pagina, element
    [a] = audit(admin_engine, "creier.versiune_aprobata", iid)
    assert a["utilizator_id"] == proprietar.id and a["tenant_id"] == tenant
    assert post(client, f"/campanii/{tenant}/{iid}/aproba", versiune="1").status_code == 409  # a doua decizie


def test_respingerea_cere_motiv_iar_o_noua_propunere_nu_inlocuieste_versiunea_aprobata(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    iid = propusa(tenant, om)
    post(client, f"/campanii/{tenant}/{iid}/aproba", versiune="1")
    propusa(tenant, om, {**strategie_valida(), "fereastra_masurare_zile": 45})
    pagina = client.get(f"/campanii/{tenant}").text
    assert "Strategia aprobată" in pagina and "Propunere în așteptare" in pagina and "versiunea 2" in pagina
    r = post(client, f"/campanii/{tenant}/{iid}/respinge", versiune="2", motiv=" ")
    assert r.status_code == 422 and "Scrie motivul" in r.text
    r = post(
        client,
        f"/campanii/{tenant}/{iid}/respinge",
        versiune="2",
        motiv="fereastra e prea lungă pentru buget",
    )
    assert r.status_code == 303
    pagina = client.get(f"/campanii/{tenant}?mesaj=respinsa").text
    assert "fereastra e prea lungă pentru buget" in pagina and "Strategia aprobată" in pagina
    with sesiune_tenant(tenant) as db:
        assert creier.versiune_aprobata(db, iid).nr == 1  # type: ignore[union-attr]
        v2 = creier.citeste(db, iid, 2)
        assert (v2.stare, v2.retras_cauza) == ("retras", "respins")
    [a] = audit(admin_engine, "creier.versiune_retrasa", iid)
    assert a["utilizator_id"] == proprietar.id and a["detalii"]["cauza"] == "respins"


def test_analistul_nu_poate_decide_nici_propune_iar_clientul_inexistent_da_404(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float], tenant: uuid.UUID, om: uuid.UUID
) -> None:
    iid = propusa(tenant, om)
    cont = fabrica_conturi(Rol.ANALIST, cu_totp=True)
    autentifica(client, cont, ceas)
    assert client.get("/campanii").status_code == 200  # citește lista
    assert post(client, f"/campanii/{tenant}/{iid}/aproba", versiune="1").status_code == 403
    assert post(client, f"/campanii/{tenant}/{iid}/respinge", versiune="1", motiv="nu").status_code == 403
    assert post(client, f"/campanii/{tenant}/propune").status_code == 403
    assert client.get(f"/campanii/{uuid.uuid4()}").status_code == 404  # un client pe care nu îl vede


def test_strategia_se_propune_din_ecran_si_apare_dupa_ce_fluxul_termina(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    pana_la_insight(tenant, om, modele)
    model_strategie(modele)
    r = post(client, f"/campanii/{tenant}/propune")
    assert r.status_code == 303 and r.headers["location"].endswith("mesaj=pornita")
    for _ in range(200):
        if "Propunere în așteptare" in client.get(f"/campanii/{tenant}").text:
            break
        time.sleep(0.1)
    else:
        raise AssertionError("strategia nu a apărut")
    iid = propusa_id(tenant)
    assert post(client, f"/campanii/{tenant}/{iid}/aproba", versiune="1").status_code == 303
    assert "Strategia aprobată" in client.get(f"/campanii/{tenant}").text


def propusa_id(tenant: uuid.UUID) -> uuid.UUID:
    with sesiune_tenant(tenant) as db:
        i = creier.gaseste_intrare(
            db, tenant_id=tenant, compartiment=Compartiment.STRATEGIE, cheie=strategie.CHEIE_STRATEGIE
        )
        assert i is not None
        return i.id
