import datetime as dt
import hashlib
import hmac
import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import select

from app.comert import oauth
from app.comert.modele import Magazin
from app.conturi import criptare
from app.db import sesiune_tenant

pytestmark = pytest.mark.db


def semneaza(p, secret):
    p = {k: v for k, v in p.items() if k != "hmac"}
    p["hmac"] = hmac.new(
        secret.encode(), "&".join(f"{k}={p[k]}" for k in sorted(p)).encode(), hashlib.sha256
    ).hexdigest()
    return p


def test_oauth_izolat(date, chei_de_test):
    shop = f"m{uuid.uuid4().hex}.myshopify.com"
    url = oauth.incepe(date.a, shop, "id", "https://ama.invalid/callback")
    state = parse_qs(urlsplit(url).query)["state"][0]
    secret, token = uuid.uuid4().hex, uuid.uuid4().hex
    p = semneaza({"shop": shop, "state": state, "code": "cod"}, secret)
    with pytest.raises(ValueError):
        oauth.termina(date.b, p, secret, lambda _: token)
    with pytest.raises(ValueError):
        oauth.termina(date.a, semneaza({**p, "state": "gresit", "hmac": ""}, secret), secret, lambda _: token)
    oauth.termina(date.a, p, secret, lambda _: token)
    with pytest.raises(ValueError):
        oauth.termina(date.a, p, secret, lambda _: token)
    with sesiune_tenant(date.a) as db:
        m = db.scalar(select(Magazin).where(Magazin.magazin == shop))
        assert m.token_criptat != token.encode()
        assert criptare.decripteaza(m.token_criptat, aad=oauth.aad(date.a, shop)).decode() == token
        with pytest.raises(InvalidTag):
            criptare.decripteaza(m.token_criptat, aad=oauth.aad(date.b, shop))
    with sesiune_tenant(date.b) as db:
        assert db.scalar(select(Magazin).where(Magazin.magazin == shop)) is None


def test_expirat(date, chei_de_test):
    shop = f"m{uuid.uuid4().hex}.myshopify.com"
    url = oauth.incepe(date.a, shop, "id", "https://ama.invalid/callback")
    state = parse_qs(urlsplit(url).query)["state"][0]
    with sesiune_tenant(date.a) as db:
        m = db.scalar(select(Magazin).where(Magazin.magazin == shop))
        m.expira_la = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    secret = uuid.uuid4().hex
    with pytest.raises(ValueError):
        oauth.termina(
            date.a, semneaza({"shop": shop, "state": state, "code": "cod"}, secret), secret, lambda _: ""
        )
