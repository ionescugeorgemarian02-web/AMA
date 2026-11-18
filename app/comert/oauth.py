"""OAuth Shopify: nucleu local; # SIMULAT: schimbul codului e injectat."""

import datetime as dt
import hashlib
import hmac
import re
import uuid
from collections.abc import Callable
from urllib.parse import parse_qsl, urlencode

from sqlalchemy import select

from app.comert.modele import Magazin
from app.conturi import criptare
from app.db import sesiune_tenant


def domeniu(text: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com", text):
        raise ValueError("Domeniu Shopify invalid")
    return text


def verifica_callback(query: bytes, secret: str) -> dict[str, str]:
    if not isinstance(query, bytes):
        raise ValueError("Este necesar query string-ul brut")
    try:
        parti = query.split(b"&")
        parametri = dict(parse_qsl(query.decode("ascii"), strict_parsing=True))
        if len(parametri) != len(parti):
            raise ValueError("Parametri duplicați")
        mesaj = b"&".join(sorted(p for p in parti if p.split(b"=", 1)[0] not in {b"hmac", b"signature"}))
        calculat = hmac.new(secret.encode(), mesaj, hashlib.sha256).hexdigest().encode()
        if not hmac.compare_digest(calculat, parametri.get("hmac", "").encode()):
            raise ValueError("Semnătură Shopify invalidă")
        timestamp = int(parametri["timestamp"])
        if not 0 <= dt.datetime.now(dt.UTC).timestamp() - timestamp <= 300:
            raise ValueError("Callback expirat")
    except (UnicodeError, KeyError, OverflowError) as exc:
        raise ValueError("Callback invalid") from exc
    return parametri


def aad(tenant: uuid.UUID, shop: str) -> bytes:
    return f"shopify:{tenant}:{domeniu(shop)}".encode()


def incepe(tenant: uuid.UUID, shop: str, client_id: str, redirect: str) -> str:
    shop = domeniu(shop)
    stare = criptare.jeton_nou()
    with sesiune_tenant(tenant) as db:
        m = db.scalar(select(Magazin).where(Magazin.magazin == shop).with_for_update())
        if m is None:
            m = Magazin(tenant_id=tenant, magazin=shop)
            db.add(m)
        m.stare_hash = criptare.hash_jeton(stare)
        m.expira_la = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=10)
    return f"https://{shop}/admin/oauth/authorize?" + urlencode(
        {
            "client_id": client_id,
            "scope": "read_products,read_orders,read_customers",
            "redirect_uri": redirect,
            "state": stare,
        }
    )


def termina(tenant: uuid.UUID, query: bytes, secret: str, schimb: Callable[[str], str]) -> None:
    parametri = verifica_callback(query, secret)
    shop = domeniu(parametri["shop"])
    with sesiune_tenant(tenant) as db:
        m = db.scalar(select(Magazin).where(Magazin.magazin == shop).with_for_update())
        if (
            m is None
            or m.stare_hash is None
            or m.expira_la is None
            or m.expira_la <= dt.datetime.now(dt.UTC)
            or not hmac.compare_digest(m.stare_hash, criptare.hash_jeton(parametri.get("state", "")))
        ):
            raise ValueError("Autorizare expirată sau nevalidă")
        tentativa = m.stare_hash
        m.expira_la = None
    token = schimb(parametri["code"])
    with sesiune_tenant(tenant) as db:
        m = db.scalar(select(Magazin).where(Magazin.magazin == shop).with_for_update())
        if m is None or m.stare_hash != tentativa or m.expira_la is not None:
            raise ValueError("Autorizare înlocuită de o încercare nouă")
        m.stare_hash = None
        m.token_criptat = criptare.cripteaza(token.encode(), aad=aad(tenant, shop))
