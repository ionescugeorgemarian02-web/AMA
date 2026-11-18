"""Catalog tenant pentru conținut și reclame; webhook-uri semnate pe corpul brut."""

import base64
import datetime as dt
import hashlib
import hmac
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.comert.modele import Magazin, Produs
from app.comert.oauth import domeniu
from app.db import sesiune_tenant


def verifica_webhook(corp: bytes, semnatura: str, secret: str) -> None:
    if len(corp) > 1_000_000:
        raise ValueError("Webhook prea mare")
    calculat = base64.b64encode(hmac.new(secret.encode(), corp, hashlib.sha256).digest())
    if not hmac.compare_digest(calculat, semnatura.encode()):
        raise ValueError("HMAC Shopify invalid")


def salveaza(tenant: uuid.UUID, shop: str, produse: list[dict[str, Any]], *, sters: bool = False) -> None:
    shop = domeniu(shop)
    with sesiune_tenant(tenant) as db:
        if db.scalar(select(Magazin.id).where(Magazin.magazin == shop)) is None:
            raise ValueError("Magazin neasociat tenantului")
        for p in produse:
            v = (
                dt.datetime.now(dt.UTC)
                if sters
                else dt.datetime.fromisoformat(str(p["updated_at"]).replace("Z", "+00:00"))
            )
            if v.tzinfo is None:
                raise ValueError("Versiune fără fus orar")
            q = insert(Produs).values(
                tenant_id=tenant,
                magazin=shop,
                id_extern=str(p["id"]),
                titlu=str(p.get("title", "")),
                detalii={
                    "descriere": str(p.get("body_html", "")),
                    "handle": str(p.get("handle", "")),
                    "imagini": [str(i["src"]) for i in p.get("images", [])],
                    "variante": [
                        {k: v.get(k) for k in ("id", "sku", "price", "inventory_quantity")}
                        for v in p.get("variants", [])
                    ],
                },
                activ=not sters,
                versiune=v,
            )
            db.execute(
                q.on_conflict_do_update(
                    index_elements=[Produs.tenant_id, Produs.magazin, Produs.id_extern],
                    set_={
                        "titlu": q.excluded.titlu,
                        "detalii": q.excluded.detalii,
                        "activ": q.excluded.activ,
                        "versiune": q.excluded.versiune,
                    },
                    where=Produs.versiune < q.excluded.versiune,
                )
            )


def lista(tenant: uuid.UUID, shop: str) -> list[dict[str, Any]]:
    with sesiune_tenant(tenant) as db:
        return [
            {"id_extern": p.id_extern, "titlu": p.titlu, "detalii": p.detalii}
            for p in db.scalars(
                select(Produs)
                .where(Produs.magazin == domeniu(shop), Produs.activ.is_(True))
                .order_by(Produs.id_extern)
            )
        ]


def webhook(tenant: uuid.UUID, shop: str, topic: str, corp: bytes, semnatura: str, secret: str) -> None:
    verifica_webhook(corp, semnatura, secret)
    if topic not in {"products/create", "products/update", "products/delete"}:
        raise ValueError("Topic nesuportat")
    p = json.loads(corp)
    # Ștergerea nu are versiune; ora recepției protejează tombstone-ul de actualizări vechi.
    salveaza(tenant, shop, [p], sters=topic == "products/delete")
