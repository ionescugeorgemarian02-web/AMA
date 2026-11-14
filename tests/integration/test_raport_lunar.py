"""F7.8 — raportul lunar, prima formă. „Gata când”: raportul se generează pentru un brand propriu. Brandul propriu
(fără utilizatori de client: aprobă operatorul agenției) e cel FICTIV; textele sunt ale modelului FALS."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app import analiza, productie, publicare
from app.conturi import Rol
from app.db import sesiune_tenant
from tests.integration.conftest import Cont, login
from tests.integration.lant_continut import fara_cereri_ramase  # noqa: F401
from tests.integration.test_portal_aprobari import lot_la_client
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fara_cereri_ramase")]
LINK = "https://www.facebook.com/cafeneauazorilor/posts/{}"


def test_raportul_se_genereaza_pentru_un_brand_propriu(
    client: TestClient, tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None,
    fabrica_conturi: Callable[..., Cont],
) -> None:  # fmt: skip
    lids = lot_la_client(tenant, om, modele, n=3)
    with sesiune_tenant(tenant, om) as db:
        cereri = [productie.aprobari.cerere_activa(db, lid) for lid in lids]
        assert all(c is not None and c.decident == productie.Decident.OPERATOR.value for c in cereri)
        for i, c in enumerate(cereri):
            assert c is not None
            if i < 2:
                productie.aprobari.decide(db, c.id, productie.Hotarare.APROBAT, utilizator_id=om,
                                          rol=Rol.PROPRIETAR, versiune=c.versiune)  # fmt: skip
            else:
                productie.aprobari.decide(db, c.id, productie.Hotarare.RESPINS, utilizator_id=om,
                                          rol=Rol.PROPRIETAR, versiune=c.versiune, motiv_standard="hook_slab")  # fmt: skip
    with sesiune_tenant(tenant, om) as db:
        for i, lid in enumerate(lids[:2]):
            [p] = publicare.asistata.ale_livrabilului(db, lid)
            publicare.asistata.confirma(db, p.id, link=LINK.format(1000 + i), utilizator_id=om)
        lv = productie.citeste(db, lids[0])
        assert lv is not None and lv.termen_la is not None
        luna = lv.termen_la.date()
    with sesiune_tenant(tenant, om) as db:
        r = analiza.raport_lunar.genereaza(db, tenant, luna, utilizator_id=om)
        c = r.continut
    postari = next(x for x in c["livrat"] if x["tip"] == "postare")
    assert postari["livrate"] >= 2 and postari["pachet"] is None  # brand propriu: fără abonament
    assert c["aprobari"]["decise"] == 3 and c["aprobari"]["din_prima"] == 2
    assert c["aprobari"]["motive_respingere"] == {"Hook slab": 1}
    assert "F10" in c["rezultate"] and c["nevoi"]
    assert set(c) == {"luna", "livrat", "rezultate", "aprobari", "public", "plan_luna_urmatoare", "nevoi"}
    with sesiune_tenant(tenant, om) as db:  # regenerarea înlocuiește, nu dublează
        analiza.raport_lunar.genereaza(db, tenant, luna)
        assert len(analiza.raport_lunar.ale_clientului(db, tenant)) == 1
    titular = fabrica_conturi(Rol.CLIENT_TITULAR, tenant_id=tenant)
    assert login(client, titular.email, titular.parola).status_code == 303
    h = client.get("/portal/rapoarte").text
    assert f"Luna {c['luna']}" in h and "1. Ce am livrat" in h and "7. Ce avem nevoie de la tine" in h
