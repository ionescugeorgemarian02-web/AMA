"""Analiza lunară a urmelor (FT.4): ce a mers bine/prost, regresii, costuri, porți picate, motive de
respingere și, pentru fiecare eșec, lanțul cauzal până la evenimentul-sursă (și cauza probabilă)."""

import datetime as dt
import json
import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ids import new_id
from app.operare.urme import indicatori
from app.operare.urme.modele import RaportUrme, Urma

RELE = ("esec", "respins", "blocat")
PRAG_REGRESIE_PP = 0.05  # rata de eșec crește cu cel puțin 5 puncte procentuale
PRAG_DURATA = 1.5  # p95 crește cu cel puțin 50%
PRAG_COST = 1.3  # costul crește cu cel puțin 30%
VOLUM_MINIM = 5  # sub atât, o componentă nu e lăudată și nici acuzată de regresie
PORTI = ("validare", "creier")
RESPINGERI = ("aprobare", "buget")
ESECURI_DETALIATE = 2000


def luna_de(moment: dt.datetime | dt.date) -> dt.date:
    return dt.date(moment.year, moment.month, 1)


def _limite(luna: dt.date) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime(luna.year, luna.month, 1, tzinfo=dt.UTC)
    urm = dt.datetime(luna.year + (luna.month == 12), luna.month % 12 + 1, 1, tzinfo=dt.UTC)
    return start, urm


def luna_precedenta(luna: dt.date) -> dt.date:
    return dt.date(luna.year - (luna.month == 1), (luna.month - 2) % 12 + 1, 1)


def _scurt(u: Urma) -> dict[str, Any]:
    return {
        "id": str(u.id), "la": u.la.isoformat(), "componenta": u.componenta, "actiune": u.actiune,
        "rezultat": u.rezultat, "cod": u.cod, "motiv": u.motiv, "actor": u.actor,
        "obiect": f"{u.obiect_tip}:{u.obiect_id}" if u.obiect_id else None,
    }  # fmt: skip


def _lanturi(db: Session, de_la: dt.datetime, pana_la: dt.datetime) -> list[dict[str, Any]]:
    """Fiecare urmă rea din lună: lanțul ei (sursa → … → eșecul) și cauza probabilă (prima rea dinăuntru)."""
    fire = (
        select(Urma.corelare_id)
        .where(Urma.la >= de_la, Urma.la < pana_la, Urma.rezultat.in_(RELE))
        .distinct()
    )
    toate = list(db.scalars(select(Urma).where(Urma.corelare_id.in_(fire)).order_by(Urma.la, Urma.id)))
    dupa_id = {u.id: u for u in toate}
    copii: dict[uuid.UUID, list[Urma]] = defaultdict(list)
    primele: dict[str, Urma] = {}
    for u in toate:
        primele.setdefault(u.corelare_id, u)
        if u.cauza_id is not None:
            copii[u.cauza_id].append(u)
    out: list[dict[str, Any]] = []
    for u in toate:
        if not (de_la <= u.la < pana_la and u.rezultat in RELE):
            continue
        lant, cur, vazute, intrerupt = [u], u, {u.id}, False
        while cur.cauza_id is not None:
            p = dupa_id.get(cur.cauza_id)
            if p is None or p.id in vazute:
                intrerupt = True
                break
            lant.append(p)
            vazute.add(p.id)
            cur = p
        sursa = lant[-1]
        if (
            intrerupt and primele[u.corelare_id].id not in vazute
        ):  # părintele lipsește: sursa = începutul firului
            sursa = primele[u.corelare_id]
            lant.append(sursa)
        out.append(
            {
                "esec": _scurt(u),
                "fir": u.corelare_id,
                "sursa": _scurt(sursa),
                "lant": [_scurt(x) for x in reversed(lant)],
                "lant_intrerupt": intrerupt,
                "cauza_probabila": _cauza_interioara(u, copii),
                "explicatie": _explica(u, sursa, _cauza_interioara(u, copii)),
            }
        )
    return out


def _cauza_interioara(u: Urma, copii: dict[uuid.UUID, list[Urma]]) -> dict[str, Any] | None:
    """Cea mai adâncă primă urmă rea dintre descendenții lui `u` (de ce a eșuat, din interior)."""
    gasit: Urma | None = None
    stiva = list(copii.get(u.id, []))
    vazute: set[uuid.UUID] = set()
    while stiva:
        c = stiva.pop(0)
        if c.id in vazute:
            continue
        vazute.add(c.id)
        if c.rezultat in RELE:
            gasit = c
            stiva = list(copii.get(c.id, []))  # coboară în eșecul găsit
    return _scurt(gasit) if gasit else None


def _explica(u: Urma, sursa: Urma, cauza: dict[str, Any] | None) -> str:
    text_ = f"{u.componenta}/{u.actiune}: {u.rezultat}"
    if u.cod:
        text_ += f" ({u.cod})"
    if u.motiv:
        text_ += f" — {u.motiv}"
    if cauza:
        text_ += (
            f"; cauza: {cauza['componenta']}/{cauza['actiune']} {cauza['rezultat']} {cauza['cod']}".rstrip()
        )
    if sursa.id != u.id:
        text_ += f"; pornit din {sursa.componenta}/{sursa.actiune} la {sursa.la:%Y-%m-%d %H:%M}"
    else:
        text_ += "; este chiar evenimentul-sursă"
    return text_


def _grupate(
    db: Session, de_la: dt.datetime, pana_la: dt.datetime, componente: tuple[str, ...], camp: str
) -> list[list[Any]]:
    q = text(
        f"SELECT componenta, actiune, {camp}, count(*) FROM urme WHERE la >= :a AND la < :b "  # noqa: S608
        "AND rezultat IN ('esec', 'respins', 'blocat') AND componenta = ANY(:c) "
        "GROUP BY 1, 2, 3 ORDER BY 4 DESC, 1, 2"
    )
    return [list(r) for r in db.execute(q, {"a": de_la, "b": pana_la, "c": list(componente)})]


def analizeaza(db: Session, luna: dt.date) -> dict[str, Any]:
    """Raportul lunii `luna` (prima zi a lunii), în comparație cu luna precedentă. Nu scrie nimic."""
    de_la, pana_la = _limite(luna)
    acum = {i.componenta: i for i in indicatori.calculeaza(db, de_la, pana_la)}
    inainte = {i.componenta: i for i in indicatori.calculeaza(db, *_limite(luna_precedenta(luna)))}
    bine, prost, regresii = [], [], []
    for c, i in acum.items():
        v = inainte.get(c)
        if i.total >= VOLUM_MINIM and i.rata_esec == 0:
            bine.append({"componenta": c, "motiv": f"{i.total} urme, niciun eșec"})
        elif v and v.total >= VOLUM_MINIM and i.rata_esec <= v.rata_esec - PRAG_REGRESIE_PP:
            bine.append(
                {
                    "componenta": c,
                    "motiv": f"rata de eșec a scăzut de la {v.rata_esec:.0%} la {i.rata_esec:.0%}",
                }
            )
        if i.rele:
            prost.append({"componenta": c, "rele": i.rele, "rata_esec": i.rata_esec, "coduri": i.coduri})
        if v is None or v.total < VOLUM_MINIM or i.total < VOLUM_MINIM:
            continue
        if i.rata_esec >= v.rata_esec + PRAG_REGRESIE_PP:
            regresii.append(
                {"componenta": c, "indicator": "rata_esec", "inainte": v.rata_esec, "acum": i.rata_esec}
            )
        if v.durata_p95_ms and i.durata_p95_ms and i.durata_p95_ms >= v.durata_p95_ms * PRAG_DURATA:
            regresii.append(
                {
                    "componenta": c,
                    "indicator": "durata_p95_ms",
                    "inainte": v.durata_p95_ms,
                    "acum": i.durata_p95_ms,
                }
            )
        for unit, cost in i.cost.items():
            vechi = v.cost.get(unit, Decimal(0))
            if vechi > 0 and cost >= vechi * Decimal(str(PRAG_COST)):
                regresii.append(
                    {
                        "componenta": c,
                        "indicator": f"cost_{unit}",
                        "inainte": float(vechi),
                        "acum": float(cost),
                    }
                )
    costuri: defaultdict[str, float] = defaultdict(float)
    for i in acum.values():
        for unit, cost in i.cost.items():
            costuri[unit] += float(cost)
    esecuri = _lanturi(db, de_la, pana_la)
    return {
        "luna": luna.isoformat(),
        "perioada": [de_la.isoformat(), pana_la.isoformat()],
        "total_urme": sum(i.total for i in acum.values()),
        "total_esecuri": len(esecuri),
        "indicatori": [i.ca_dict() for i in acum.values()],
        "bine": bine,
        "prost": sorted(prost, key=lambda x: -x["rele"]),
        "regresii": regresii,
        "costuri": {
            "total": dict(costuri),
            "pe_componenta": {c: {u: float(v) for u, v in i.cost.items()} for c, i in acum.items() if i.cost},
        },
        "porti_picate": _grupate(db, de_la, pana_la, PORTI, "cod"),
        "motive_respingere": _grupate(db, de_la, pana_la, RESPINGERI, "motiv"),
        "esecuri": esecuri[:ESECURI_DETALIATE],
        "esecuri_netaiate": len(esecuri) <= ESECURI_DETALIATE,
    }


def genereaza(db: Session, luna: dt.date) -> dict[str, Any]:
    """Analizează și salvează (înlocuiește) raportul lunii. Cere sesiune de agenție."""
    continut: dict[str, Any] = json.loads(
        json.dumps(analizeaza(db, luna))
    )  # exact forma salvată (tuplurile devin liste)
    db.execute(
        insert(RaportUrme)
        .values(id=new_id(), luna=luna, continut=continut)
        .on_conflict_do_update(
            index_elements=["luna"], set_={"continut": continut, "generat_la": dt.datetime.now(dt.UTC)}
        )
    )
    return continut


def raport(db: Session, luna: dt.date) -> dict[str, Any] | None:
    return db.scalar(select(RaportUrme.continut).where(RaportUrme.luna == luna))


def luni_cu_raport(db: Session) -> list[dt.date]:
    return list(db.scalars(select(RaportUrme.luna).order_by(RaportUrme.luna.desc())))
