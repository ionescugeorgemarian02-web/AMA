import hashlib
import hmac
import uuid

import httpx
import pytest

from app.comert import oauth
from app.connectors.comert import ShopifySimulat


def test_domenii():
    assert oauth.domeniu("exemplu.myshopify.com") == "exemplu.myshopify.com"
    for v in ["evil.com", "x.myshopify.com/a", "x.myshopify.com.evil.com", "https://x.myshopify.com"]:
        with pytest.raises(ValueError):
            oauth.domeniu(v)


def test_callback_hmac():
    p = {"shop": "exemplu.myshopify.com", "state": "abc", "code": "cod"}
    secret = uuid.uuid4().hex
    p["hmac"] = hmac.new(
        secret.encode(), "&".join(f"{k}={p[k]}" for k in sorted(p)).encode(), hashlib.sha256
    ).hexdigest()
    oauth.verifica_callback(p, secret)
    p["code"] = "altul"
    with pytest.raises(ValueError):
        oauth.verifica_callback(p, secret)


def test_schimb_http_local():
    def raspunde(r):
        assert r.url.path == "/admin/oauth/access_token"
        return httpx.Response(200, json={"access_token": uuid.uuid4().hex})

    c = ShopifySimulat(httpx.MockTransport(raspunde))
    assert c.schimba_cod("cod", "id", uuid.uuid4().hex)


def test_refuza_transport_real():
    with pytest.raises(ValueError):
        ShopifySimulat(httpx.HTTPTransport())


@pytest.mark.parametrize("status,corp", [(401, {}), (429, {}), (200, {}), (200, {"access_token": ""})])
def test_schimb_refuzat(status, corp):
    c = ShopifySimulat(httpx.MockTransport(lambda _: httpx.Response(status, json=corp)))
    with pytest.raises(ValueError):
        c.schimba_cod("cod", "id", uuid.uuid4().hex)
