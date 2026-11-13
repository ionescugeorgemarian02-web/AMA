"""F4.5 — ecranul ghidului de brand: propune variante, alege sau combină, cu CSRF și permisiune."""

# ruff: noqa: F811
import time
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app import creier
from app.conturi import Rol
from app.creier.compartimente import Compartiment
from app.db import sesiune_tenant
from app.onboarding import ghid
from tests.integration.conftest import Cont
from tests.integration.test_onboarding_ghid import brief_aprobat, inregistreaza, tre_variante
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401

pytestmark = pytest.mark.db
Fabrica = Callable[..., Cont]


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


def test_ghidul_se_propune_si_se_alege_din_panou(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    inregistreaza(modele, tre_variante())
    pagina = client.get(f"/onboarding/{tenant}/ghid").text
    assert "Brieful nu este aprobat" in pagina and "Propune variante" not in pagina
    brief_aprobat(tenant, om)
    assert "Propune variante de ton" in client.get(f"/onboarding/{tenant}/ghid").text
    assert client.post(f"/onboarding/{tenant}/ghid/propune", data={}).status_code == 403  # fără CSRF
    r = client.post(
        f"/onboarding/{tenant}/ghid/propune", data={"csrf_token": csrf(client)}, follow_redirects=False
    )
    assert r.status_code == 303
    for _ in range(100):
        with sesiune_tenant(tenant) as db:
            if ghid.variante(db, tenant):
                break
        time.sleep(0.1)
    pagina = client.get(f"/onboarding/{tenant}/ghid").text
    for nr, nume in ((1, "Barista prietenos"), (2, "Expertul calm"), (3, "Vecinul vesel")):
        assert f"Varianta {nr} · {nume}" in pagina
    assert "Vocabular interzis:" in pagina and "Alege varianta 3" in pagina
    r = client.post(f"/onboarding/{tenant}/ghid/alege", data={"varianta": "9", "csrf_token": csrf(client)})
    assert r.status_code == 422 and "nu există" in r.text
    r = client.post(
        f"/onboarding/{tenant}/ghid/alege",
        data={"varianta": "2", "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    r = client.post(
        f"/onboarding/{tenant}/ghid/alege",
        data={
            "parte_descriere": "1",
            "parte_reguli": "2",
            "parte_vocabular": "3",
            "parte_exemple": "1",
            "csrf_token": csrf(client),
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    with sesiune_tenant(tenant) as db:
        i = creier.gaseste_intrare(db, tenant_id=tenant, compartiment=Compartiment.PROFIL_BRAND, cheie="ghid")
        assert i is not None
        istoric = creier.istoric(db, i.id)
        assert [v.nr for v in istoric] == [1, 2] and [v.continut["origine"] for v in istoric] == [
            "varianta",
            "combinat",
        ]
