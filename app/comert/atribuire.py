"""Atribuire declarativă UTM/cod, agregată pe luna UTC, fără conversii valutare."""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.comert import vanzari
from app.comert.modele import DateComert


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


def materiale(
    db: Session, tenant_id: uuid.UUID, inceput: dt.datetime, sfarsit: dt.datetime
) -> dict[str, Any]:
    """Comenzi importate pe interval UTC, grupate pe material, sursă, campanie și monedă."""
    randuri = db.scalars(
        select(DateComert.date).where(
            DateComert.tenant_id == tenant_id,
            DateComert.tip == "comanda",
            DateComert.creata_la >= inceput,
            DateComert.creata_la < sfarsit,
        )
    )
    grupuri: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    volum = 0
    for c in randuri:
        volum += 1
        if c.get("anulata"):
            continue
        cheie = tuple(str(c.get(k) or "necunoscut") for k in ("utm_content", "utm_campaign", "utm_source"))
        material, campanie, canal = cheie
        moneda = str(c["moneda"])
        g = grupuri.setdefault(
            (material, campanie, canal, moneda),
            {
                "material": material,
                "campanie": campanie,
                "canal": canal,
                "moneda": moneda,
                "comenzi": 0,
                "net_bani": 0,
            },
        )
        g["comenzi"] += 1
        g["net_bani"] += max(0, int(str(c["total_bani"])) - int(str(c.get("rambursat_bani", 0))))
    programari = db.execute(
        text(
            "SELECT livrabil_id, SUM(numar) AS numar, COUNT(*) AS zile FROM programari_material "
            "WHERE tenant_id=:tid AND zi >= :inceput AND zi < :sfarsit "
            "GROUP BY livrabil_id ORDER BY livrabil_id"
        ),
        {"tid": tenant_id, "inceput": inceput.date(), "sfarsit": sfarsit.date()},
    )
    return {
        "programari": [{"material": str(lid), "numar": int(n), "zile": z} for lid, n, z in programari],
        "comenzi_importate": volum,
        "materiale": [grupuri[k] for k in sorted(grupuri)],
    }
