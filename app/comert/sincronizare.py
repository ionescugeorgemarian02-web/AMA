"""Sincronizare locală cu cititori injectați; fără importuri de conector în domeniu."""

import datetime as dt
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select

from app.comert import catalog, oauth, vanzari
from app.comert.modele import Magazin, Sincronizare
from app.conturi import criptare
from app.db import sesiune_tenant


def executa(
    tenant: uuid.UUID,
    shop: str,
    produse: Callable[[str], list[dict[str, Any]]],
    date: Callable[[str, str], list[dict[str, Any]]],
) -> None:
    shop = oauth.domeniu(shop)
    with sesiune_tenant(tenant) as db:
        m = db.scalar(select(Magazin).where(Magazin.magazin == shop))
        if m is None or m.token_criptat is None:
            raise ValueError("Magazin neconectat")
        token = criptare.decripteaza(m.token_criptat, aad=oauth.aad(tenant, shop)).decode()
        s = db.get(Sincronizare, (tenant, shop))
        if s is None:
            s = Sincronizare(tenant_id=tenant, magazin=shop, stare="in_curs")
            db.add(s)
        s.stare = "in_curs"
    try:
        catalog.salveaza(tenant, shop, produse(token))
        invalide = []
        for tip in ("comanda", "client"):
            invalide.extend(vanzari.importa(tenant, shop, tip, date(tip, token)))
        if invalide:
            raise ValueError("Lot cu rânduri invalide")
    except Exception:
        with sesiune_tenant(tenant) as db:
            s = db.get(Sincronizare, (tenant, shop))
            if s is not None:
                s.stare = "eroare"
        raise ValueError("Sincronizarea Shopify a eșuat; datele pot fi parțiale") from None
    with sesiune_tenant(tenant) as db:
        s = db.get(Sincronizare, (tenant, shop))
        if s is not None:
            s.stare = "succes"
            s.ultima_reusita = dt.datetime.now(dt.UTC)
