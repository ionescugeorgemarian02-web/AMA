"""F12.10 — asistentul de suport din portal. „Gata când”: o întrebare despre starea unui livrabil primește
răspuns corect, iar o întrebare despre facturare sau o reclamație ajunge la tine."""

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.comert import oauth, vanzari
from app.conturi import Rol
from app.db import sesiune_agentie, sesiune_tenant
from app.portal import suport
from tests.integration.conftest import Cont, csrf_din, login
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import livrabil

pytestmark = pytest.mark.db


def intreaba(client: TestClient, intrebare: str) -> str:
    h = client.get("/portal/suport")
    assert h.status_code == 200 and "asistentul AI" in h.text
    r = client.post("/portal/suport", data={"csrf_token": csrf_din(h.text), "intrebare": intrebare})
    assert r.status_code == 200
    return r.text


def test_livrabilul_primeste_raspuns_corect_iar_facturarea_si_reclamatia_ajung_la_tine(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float], admin_engine: Engine,
    chei_de_test: None,
) -> None:  # fmt: skip
    titular = fabrica_conturi(Rol.CLIENT_TITULAR)
    tenant = titular.tenant_id
    assert tenant is not None
    termen = dt.datetime.now(dt.UTC) + dt.timedelta(days=3)
    livrabil(tenant, tip="video", canal="instagram", termen_la=termen)
    livrabil(tenant, tip="postare", canal="facebook")
    alt = fabrica_conturi(Rol.CLIENT_TITULAR)  # alt client, cu un livrabil pe instagram: nu trebuie să apară
    assert alt.tenant_id is not None
    livrabil(alt.tenant_id, tip="video", canal="instagram")
    assert login(client, titular.email, titular.parola).status_code == 303

    h = intreaba(client, "Ce se întâmplă cu clipul video de pe Instagram?")
    assert (
        f"Livrabilele tale de tip video pe instagram: 1 planificat. Următorul: video pe instagram, termen {termen:%d.%m.%Y}, stare: planificat."
        in h
    )
    assert "1 planificat" in intreaba(client, "Care e starea postărilor pe facebook?")
    assert "1 persoană cu acces" in intreaba(client, "Cum îmi schimb parola contului?")

    # magazinul Shopify: doar clienții cu acord, prin exportul comerțului
    shop = f"m{uuid.uuid4().hex[:10]}.myshopify.com"
    oauth.incepe(tenant, shop, "id", "https://ama.invalid/callback")
    vanzari.importa(tenant, shop, "client", [
        {"id": "1", "updated_at": "2026-11-18T12:00:00Z", "email": "a@x.test", "email_marketing_consent": {"state": "subscribed"}},
        {"id": "2", "updated_at": "2026-11-18T12:00:00Z", "email": "b@x.test"},
    ])  # fmt: skip
    assert f"Magazinul {shop} are acum 1 clienți cu acord de email" in intreaba(
        client, f"Câți abonați are {shop}?"
    )

    for q, _cat in (("Nu găsesc factura pe octombrie, mi-ați luat banii de două ori", "facturare"),
                   ("Sunt nemulțumit, vreau să fac o reclamație", "reclamatie"),
                   ("Puteți să-mi faceți și un logo?", "altceva")):  # fmt: skip
        assert "unui om din echipă" in intreaba(client, q)
    with sesiune_tenant(tenant) as db:
        cats = {i.intrebare: (i.categorie, i.escaladat) for i in suport.istoric(db, tenant)}
    assert cats["Sunt nemulțumit, vreau să fac o reclamație"] == ("reclamatie", True)
    assert cats["Ce se întâmplă cu clipul video de pe Instagram?"] == ("livrabile", False)
    with sesiune_tenant(alt.tenant_id) as db:
        assert suport.istoric(db, alt.tenant_id) == [], "un client nu vede întrebările altuia"

    # ajung la tine: ecranul proprietarului, cu preluare
    client.cookies.clear()
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    h = client.get("/crm/suport").text
    assert (
        "mi-ați luat banii de două ori" in h and "vreau să fac o reclamație" in h and "clipul video" not in h
    )
    with sesiune_agentie() as db:
        primul = suport.escaladate(db)[0].id
    jeton = csrf(client, "/crm/suport")
    assert (
        client.post(
            f"/crm/suport/{primul}/preia", data={"csrf_token": jeton}, follow_redirects=False
        ).status_code
        == 303
    )
    with sesiune_agentie() as db:
        assert primul not in {i.id for i in suport.escaladate(db)}
    with admin_engine.begin() as c:
        n = c.execute(
            text(
                "SELECT count(*) FROM urme WHERE componenta = 'portal' AND actiune = 'suport' AND tenant_id = :t"
            ),
            {"t": tenant},
        ).scalar_one()
    assert n == 7


@pytest.mark.parametrize(
    ("intrebare", "categorie"),
    [("Când se publică articolul?", "livrabile"), ("Cât costă abonamentul?", "facturare"),
     ("Vreau să reziliez, e inacceptabil", "reclamatie"), ("Am uitat parola", "cont"), ("Salut", "altceva")],
)  # fmt: skip
def test_categoriile(intrebare: str, categorie: str) -> None:
    assert suport.categorie(intrebare) == categorie
