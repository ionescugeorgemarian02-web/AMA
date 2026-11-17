import uuid

import pytest

from app.comert import oauth, vanzari

pytestmark = pytest.mark.db


def test_comenzi_clienti_consimtamant(date, chei_de_test):
    shop = f"m{uuid.uuid4().hex}.myshopify.com"
    oauth.incepe(date.a, shop, "id", "https://ama.invalid/callback")
    comanda = {"id": "1", "updated_at": "2026-11-17T12:00:00Z", "total_price": "12.34", "currency": "RON"}
    for _ in range(2):
        vanzari.importa(date.a, shop, "comanda", [comanda])
    assert len(vanzari.citeste(date.a, shop, "comanda")) == 1
    assert vanzari.citeste(date.a, shop, "comanda")[0]["total_bani"] == 1234
    assert vanzari.citeste(date.b, shop, "comanda") == []
    persoana = {"id": "2", "updated_at": "2026-11-17T12:00:00Z", "email": "ana@example.test"}
    vanzari.importa(date.a, shop, "client", [persoana])
    assert vanzari.pentru_crm(date.a, shop) == []
    persoana.update(updated_at="2026-11-18T12:00:00Z", email_marketing_consent={"state": "subscribed"})
    vanzari.importa(date.a, shop, "client", [persoana])
    assert vanzari.pentru_crm(date.a, shop)[0]["email"] == "ana@example.test"
    assert "ana@example.test" not in str(vanzari.citeste(date.a, shop, "client"))
    persoana.update(updated_at="2026-11-19T12:00:00Z", email_marketing_consent={"state": "unsubscribed"})
    vanzari.importa(date.a, shop, "client", [persoana])
    assert vanzari.pentru_crm(date.a, shop) == []
