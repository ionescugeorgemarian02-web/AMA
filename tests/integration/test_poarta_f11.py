"""Poarta F11 — „o lecție promovată și una retrasă, ambele cu urmă completă”, cap-coadă: postări măsurate →
Reflectorul propune → omul aprobă din panou → lecția ajunge în contextul autorului → omul anulează
promovarea din panou → lecția iese din context. Urma: lotul, dovezile, cine și când a decis, jurnalul."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.conturi import Rol
from app.db import sesiune_tenant
from app.invatare import reflector
from tests.integration.conftest import Cont
from tests.integration.test_invatare_curator import context
from tests.integration.test_invatare_ecran import _dezghetat, lectie  # noqa: F401
from tests.integration.test_invatare_reflector import postare_masurata
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, livrabil, tenant  # noqa: F401

pytestmark = pytest.mark.db


def test_o_lectie_promovata_si_una_retrasa_cu_urma_completa(
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
    tenant: uuid.UUID,
    admin_engine: Engine,
) -> None:
    for _ in range(12):
        postare_masurata(admin_engine, tenant, "cifra", 0.02)
    bune = [postare_masurata(admin_engine, tenant, "intrebare", 0.09) for _ in range(8)]
    with sesiune_tenant(tenant) as db:
        lot = reflector.reflecteaza(db, tenant)
        assert lot is not None
        [propusa] = [x for x in reflector.propuneri(db, tenant) if x.cheie.endswith("intrebare:mai_des")]
        lid, text_lectie = propusa.id, propusa.text
    assert text_lectie not in context(tenant, livrabil(tenant)), "o propunere nu schimbă nimic singură"

    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    assert text_lectie in client.get("/invatare").text
    jeton = csrf(client, "/invatare")

    # promovarea
    assert client.post(f"/invatare/lectie/{lid}/aproba", data={"csrf_token": jeton}, follow_redirects=False).status_code == 303  # fmt: skip
    assert text_lectie in context(tenant, livrabil(tenant)), "lecția aprobată intră în contextul autorului"

    # revenirea
    r = client.post(
        f"/invatare/lectie/{lid}/retrage",
        data={"csrf_token": jeton, "motiv": "tonul nu se potrivește brandului"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert text_lectie not in context(tenant, livrabil(tenant)), "lecția retrasă iese din context"

    # urma completă
    r_lectie = lectie(tenant, lid)
    assert r_lectie.stare == "retrasa" and r_lectie.lot_id == lot.id and r_lectie.decis_de is not None
    assert r_lectie.motiv == "tonul nu se potrivește brandului" and r_lectie.decis_la is not None
    assert {d["livrabil_id"] for d in r_lectie.dovezi} == {str(i) for i in bune}, "dovezile rămân pe lecție"
    with admin_engine.connect() as c:
        urma = c.execute(
            text(
                "SELECT actiune, actor_tip, utilizator_id IS NOT NULL FROM jurnal_audit "
                "WHERE tenant_id = :t AND actiune LIKE 'invatare.%' ORDER BY creat_la, id"
            ),
            {"t": tenant},
        ).all()
    assert [tuple(x) for x in urma] == [
        ("invatare.lot_reflectat", "sistem", False),
        ("invatare.lectie_aprobata", "utilizator", True),
        ("invatare.lectie_retrasa", "utilizator", True),
    ]
    h = client.get(f"/invatare?client={tenant}").text
    assert "<td>retrasă</td>" in h and "tonul nu se potrivește brandului" in h
