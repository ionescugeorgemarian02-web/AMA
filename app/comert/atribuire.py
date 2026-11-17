"""Atribuire declarativă UTM/cod, agregată pe luna UTC, fără conversii valutare."""

import datetime as dt
import uuid
from typing import Any

from app.comert import vanzari


def calculeaza(
    comenzi: list[dict[str, Any]], luna: dt.date, coduri: dict[str, tuple[str, str]]
) -> dict[tuple[str, str, str], int]:
    rezultat: dict[tuple[str, str, str], int] = {}
    for c in comenzi:
        la = dt.datetime.fromisoformat(c["creata_la"].replace("Z", "+00:00"))
        if la.tzinfo is None:
            raise ValueError("Comandă fără fus orar")
        la = la.astimezone(dt.UTC)
        if (la.year, la.month) != (luna.year, luna.month) or c.get("anulata"):
            continue
        campanie = c.get("utm_campaign")
        canal = c.get("utm_source")
        if not campanie and not canal:
            campanie, canal = coduri.get(c.get("cod_reducere", ""), ("necunoscut", "necunoscut"))
        cheie = (campanie or "necunoscut", canal or "necunoscut", c["moneda"])
        net = max(0, c["total_bani"] - max(0, c.get("rambursat_bani", 0)))
        rezultat[cheie] = rezultat.get(cheie, 0) + net
    return rezultat


def raport_lunar(
    tenant: uuid.UUID, shop: str, luna: dt.date, coduri: dict[str, tuple[str, str]]
) -> list[dict[str, Any]]:
    return [
        {"campanie": k[0], "canal": k[1], "moneda": k[2], "vanzari_nete_bani": v}
        for k, v in sorted(calculeaza(vanzari.citeste(tenant, shop, "comanda"), luna, coduri).items())
    ]
