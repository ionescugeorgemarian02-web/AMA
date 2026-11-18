import base64
import hashlib
import hmac
import json
import uuid

import pytest

from app.comert import catalog

pytestmark = pytest.mark.db


def test_catalog_hmac_idempotenta_si_izolare(date, chei_de_test):
    from app.comert import oauth

    shop = f"m{uuid.uuid4().hex}.myshopify.com"
    oauth.incepe(date.a, shop, "id", "https://ama.invalid/callback")
    secret = uuid.uuid4().hex
    corp = json.dumps({"id": "1", "title": "Produs", "updated_at": "2026-11-17T12:00:00Z"}).encode()
    sig = base64.b64encode(hmac.new(secret.encode(), corp, hashlib.sha256).digest()).decode()
    with pytest.raises(ValueError):
        catalog.webhook(date.a, shop, "products/update", corp, "gresit", secret)
    assert catalog.lista(date.a, shop) == []
    for _ in range(2):
        catalog.webhook(date.a, shop, "products/update", corp, sig, secret)
    assert len(catalog.lista(date.a, shop)) == 1
    assert catalog.lista(date.b, shop) == []
    catalog.salveaza(date.a, shop, [{"id": "1", "title": "Vechi", "updated_at": "2026-11-16T12:00:00Z"}])
    assert catalog.lista(date.a, shop)[0]["titlu"] == "Produs"
    catalog.salveaza(date.a, shop, [{"id": "1", "updated_at": "2026-11-18T12:00:00Z"}], sters=True)
    assert catalog.lista(date.a, shop) == []
    catalog.salveaza(date.a, shop, [{"id": "1", "title": "Produs", "updated_at": "2026-11-17T12:00:00Z"}])
    assert catalog.lista(date.a, shop) == []


def test_delete_doar_id(date, chei_de_test):
    from app.comert import oauth

    shop = f"m{uuid.uuid4().hex}.myshopify.com"
    oauth.incepe(date.a, shop, "id", "https://ama.invalid/callback")
    catalog.salveaza(date.a, shop, [{"id": 1, "title": "Produs", "updated_at": "2026-01-01T00:00:00Z"}])
    corp = b'{"id":1}'
    secret = uuid.uuid4().hex
    sig = base64.b64encode(hmac.new(secret.encode(), corp, hashlib.sha256).digest()).decode()
    for _ in range(2):
        catalog.webhook(date.a, shop, "products/delete", corp, sig, secret)
    assert catalog.lista(date.a, shop) == []
    catalog.salveaza(date.a, shop, [{"id": 1, "updated_at": "2026-01-02T00:00:00Z"}])
    assert catalog.lista(date.a, shop) == []
