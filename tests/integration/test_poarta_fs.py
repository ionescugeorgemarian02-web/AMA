import base64
import datetime as dt
import hashlib
import hmac
import json
import uuid
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from app.comert import atribuire, catalog, oauth, vanzari
from app.comert.sincronizare import executa
from app.connectors.comert import ShopifySimulat
from app.conturi import Rol
from tests.integration.utile_panou import autentifica


def test_poarta_fs(client, fabrica_conturi, ceas):
    cont = fabrica_conturi(Rol.CLIENT_TITULAR, cu_totp=True)
    tenant = cont.tenant_id
    shop = f"m{uuid.uuid4().hex}.myshopify.com"
    secret, token = uuid.uuid4().hex, uuid.uuid4().hex
    acum = dt.datetime.now(dt.UTC).isoformat()
    produs = {
        "id": "p1",
        "title": "Produs local",
        "updated_at": acum,
        "handle": "produs",
        "variants": [{"id": "v1", "sku": "SKU", "price": "12.34"}],
        "images": [{"src": "https://imagini.invalid/p.jpg"}],
    }
    comanda = {
        "id": "o1",
        "total_price": "12.34",
        "currency": "RON",
        "created_at": acum,
        "updated_at": acum,
        "utm_source": "meta",
        "utm_campaign": "campanie",
    }
    persoana = {
        "id": "c1",
        "email": "ana@example.test",
        "updated_at": acum,
        "email_marketing_consent": {"state": "subscribed"},
    }

    def raspunde(r):
        if r.url.path == "/admin/oauth/access_token":
            return httpx.Response(200, json={"access_token": token})
        assert r.headers["X-Shopify-Access-Token"] == token
        if r.url.path == "/catalog":
            return httpx.Response(200, json={"produse": [produs]})
        return httpx.Response(200, json=[comanda] if r.url.path.endswith("/comanda") else [persoana])

    c = ShopifySimulat(httpx.MockTransport(raspunde))
    url = oauth.incepe(tenant, shop, "client-id", "https://ama.invalid/callback")
    p = {"shop": shop, "state": parse_qs(urlsplit(url).query)["state"][0], "code": "cod"}
    p["timestamp"] = str(int(dt.datetime.now(dt.UTC).timestamp()))
    p["hmac"] = hmac.new(
        secret.encode(), "&".join(f"{k}={p[k]}" for k in sorted(p)).encode(), hashlib.sha256
    ).hexdigest()
    oauth.termina(tenant, urlencode(p).encode(), secret, lambda cod: c.schimba_cod(cod, "client-id", secret))
    executa(tenant, shop, c.catalog, c.vanzari)
    assert catalog.lista(tenant, shop)[0]["detalii"]["variante"][0]["sku"] == "SKU"
    assert len(vanzari.pentru_crm(tenant, shop)) == 1
    corp = json.dumps(produs).encode()
    sig = base64.b64encode(hmac.new(secret.encode(), corp, hashlib.sha256).digest()).decode()
    for _ in range(2):
        catalog.webhook(tenant, shop, "products/update", corp, sig, secret)
    assert len(catalog.lista(tenant, shop)) == 1
    persoana["updated_at"] = (dt.datetime.now(dt.UTC) + dt.timedelta(seconds=1)).isoformat()
    persoana["email_marketing_consent"] = {"state": "unsubscribed"}
    vanzari.importa(tenant, shop, "client", [persoana])
    assert vanzari.pentru_crm(tenant, shop) == []
    assert atribuire.raport_lunar(tenant, shop, dt.datetime.now(dt.UTC).date(), {}) == [
        {"campanie": "campanie", "canal": "meta", "moneda": "RON", "vanzari_nete_bani": 1234}
    ]
    autentifica(client, cont, ceas)
    r = client.get("/comert")
    assert r.status_code == 200
    assert shop in r.text and "succes" in r.text and "1234" in r.text
    assert token not in r.text and secret not in r.text and "ana@example.test" not in r.text
