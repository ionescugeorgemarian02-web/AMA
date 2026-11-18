"""Comenzi pentru analiză și contacte pentru CRM-ul tenantului, niciodată CRM agenție."""

import datetime as dt
import json
import uuid
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.comert.modele import DateComert, Magazin
from app.comert.oauth import aad, domeniu
from app.conturi import criptare
from app.db import sesiune_tenant

# SIX ISO 4217 list-one.xml, publicată 2026-09-17; fără acces la rețea la import.
EXPONENTI = json.loads(Path(__file__).with_name("iso4217.json").read_text())


def bani(valoare: object, moneda: str) -> int:
    if moneda not in EXPONENTI:
        raise ValueError("Monedă ISO 4217 invalidă")
    valoare_decimala = Decimal(str(valoare))
    with localcontext() as context:
        context.prec = max(28, len(valoare_decimala.as_tuple().digits) + EXPONENTI[moneda] + 1)
        suma = valoare_decimala * (10 ** EXPONENTI[moneda])
    if not suma.is_finite() or suma < 0 or suma != suma.to_integral_value():
        raise ValueError("Sumă invalidă")
    return int(suma)


def moment(valoare: str) -> dt.datetime:
    la = dt.datetime.fromisoformat(valoare.replace("Z", "+00:00"))
    if la.tzinfo is None:
        raise ValueError("Lipsește fusul orar")
    return la.astimezone(dt.UTC)


def importa(tenant: uuid.UUID, shop: str, tip: str, randuri: list[dict[str, Any]]) -> list[dict[str, object]]:
    invalide: list[dict[str, object]] = []
    if tip not in {"comanda", "client"}:
        raise ValueError("Tip neacceptat")
    shop = domeniu(shop)
    with sesiune_tenant(tenant) as db:
        if db.scalar(select(Magazin.id).where(Magazin.magazin == shop)) is None:
            raise ValueError("Magazin neasociat")
        for r in randuri:
            try:
                ident = str(r["id"])
                versiune = dt.datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
                if versiune.tzinfo is None:
                    raise ValueError("Lipsește fusul orar")
                email = None
                creata_la = None
                date: dict[str, Any]
                if tip == "comanda":
                    moneda = str(r["currency"])
                    suma = bani(r["total_price"], moneda)
                    creata_la = moment(r["created_at"])
                    date = {
                        "total_bani": int(suma),
                        "creata_la": creata_la.isoformat(),
                        "moneda": str(r["currency"]),
                        "utm_source": str(r.get("utm_source", "")),
                        "utm_campaign": str(r.get("utm_campaign", "")),
                        "cod_reducere": str(r.get("cod_reducere", "")),
                        "anulata": bool(r.get("cancelled_at")),
                        "rambursat_bani": bani(r.get("rambursat_bani", 0), moneda),
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
            except (ValueError, KeyError, TypeError, InvalidOperation):
                invalide.append({"id_extern": str(r.get("id", "")), "stare": "invalid"})
                continue
            q = insert(DateComert).values(
                tenant_id=tenant,
                magazin=shop,
                tip=tip,
                id_extern=ident,
                date=date,
                email_criptat=email,
                creata_la=creata_la,
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
                        "creata_la": q.excluded.creata_la,
                        "email_criptat": q.excluded.email_criptat,
                        "versiune": q.excluded.versiune,
                    },
                    where=DateComert.versiune < q.excluded.versiune,
                )
            )

    return invalide


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
