"""Comenzi pentru analiză și contacte pentru CRM-ul tenantului, niciodată CRM agenție."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.comert.modele import DateComert, Magazin
from app.comert.oauth import aad, domeniu
from app.conturi import criptare
from app.db import sesiune_tenant


def importa(tenant: uuid.UUID, shop: str, tip: str, randuri: list[dict[str, Any]]) -> None:
    if tip not in {"comanda", "client"}:
        raise ValueError("Tip neacceptat")
    shop = domeniu(shop)
    with sesiune_tenant(tenant) as db:
        if db.scalar(select(Magazin.id).where(Magazin.magazin == shop)) is None:
            raise ValueError("Magazin neasociat")
        for r in randuri:
            ident = str(r["id"])
            versiune = dt.datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
            if versiune.tzinfo is None:
                raise ValueError("Lipsește fusul orar")
            email = None
            date: dict[str, Any]
            if tip == "comanda":
                suma = Decimal(str(r["total_price"])) * 100
                if not suma.is_finite() or suma != suma.to_integral_value():
                    raise ValueError("Sumă invalidă")
                date = {
                    "total_bani": int(suma),
                    "creata_la": str(r["created_at"]),
                    "moneda": str(r["currency"]),
                    "utm_source": str(r.get("utm_source", "")),
                    "utm_campaign": str(r.get("utm_campaign", "")),
                    "cod_reducere": str(r.get("cod_reducere", "")),
                    "anulata": bool(r.get("cancelled_at")),
                    "rambursat_bani": int(r.get("rambursat_bani", 0)),
                }
            else:
                acord = r.get("email_marketing_consent") or {}
                date = {
                    "consimtamant": acord.get("state") == "subscribed",
                    "sursa": "shopify",
                    "dovada_la": r["updated_at"],
                }
                if r.get("email"):
                    email = criptare.cripteaza(
                        str(r["email"]).encode(), aad=aad(tenant, shop) + ident.encode()
                    )
            q = insert(DateComert).values(
                tenant_id=tenant,
                magazin=shop,
                tip=tip,
                id_extern=ident,
                date=date,
                email_criptat=email,
                versiune=versiune,
            )
            db.execute(
                q.on_conflict_do_update(
                    index_elements=[
                        DateComert.tenant_id,
                        DateComert.magazin,
                        DateComert.tip,
                        DateComert.id_extern,
                    ],
                    set_={
                        "date": q.excluded.date,
                        "email_criptat": q.excluded.email_criptat,
                        "versiune": q.excluded.versiune,
                    },
                    where=DateComert.versiune < q.excluded.versiune,
                )
            )


def citeste(tenant: uuid.UUID, shop: str, tip: str) -> list[dict[str, Any]]:
    with sesiune_tenant(tenant) as db:
        return [
            {"id_extern": r.id_extern, **r.date}
            for r in db.scalars(
                select(DateComert).where(DateComert.magazin == domeniu(shop), DateComert.tip == tip)
            )
        ]


def pentru_crm(tenant: uuid.UUID, shop: str) -> list[dict[str, Any]]:
    """Fotografie curentă; consumatorul trebuie să reverifice înainte de orice trimitere (F12)."""
    with sesiune_tenant(tenant) as db:
        rezultat = []
        for r in db.scalars(
            select(DateComert).where(DateComert.magazin == domeniu(shop), DateComert.tip == "client")
        ):
            if r.date.get("consimtamant") is True and r.email_criptat is not None:
                email = criptare.decripteaza(
                    r.email_criptat, aad=aad(tenant, shop) + r.id_extern.encode()
                ).decode()
                rezultat.append({"id_extern": r.id_extern, "email": email, **r.date})
        return rezultat
