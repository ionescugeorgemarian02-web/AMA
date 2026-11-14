"""Curba de retenție a clipurilor (F10.2, K2). Doar YouTube o dă prin API (docs/03): 100 de puncte, de la
începutul la sfârșitul clipului.

- **Când se citește.** De colector, după citirea reușită a metricilor de la 72 de ore, 7 zile și 28 de zile
  (datele Analytics apar cu 2–3 zile întârziere [I], deci la 1 oră și 24 de ore nu ar exista). Fiecare citire
  o înlocuiește pe cea veche. O citire eșuată nu strică nimic: se încearcă din nou la intervalul următor.
- **Ce se acceptă.** Cel puțin `MINIM_PUNCTE` puncte, cu poziții între 0 și 1 și valori între 0 și
  `PLAFON` (peste 1 = pasaj revăzut). O curbă care nu respectă forma e refuzată, nu „reparată”.
- **Ce se calculează din ea** (`rezumat`, pur): retenția medie, retenția după primele 10% din clip (cât ține
  hook-ul), retenția la final și cea mai mare cădere între două puncte vecine (unde pleacă lumea).
- **Cum se desenează** (`linie_svg`, pur): coordonatele unei linii SVG, randate pe server (fără bibliotecă
  de grafice, ADR-13).
"""

import datetime as dt
import itertools
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.analiza.modele import CurbaRetentie
from app.db import sesiune_tenant
from app.ids import new_id
from app.logging import get_logger
from app.operare import motor
from app.operare.efecte import metrici as usa_metrici

log = get_logger("app.analiza.retentie")
INTERVALE_CU_CURBA = frozenset({"72h", "7z", "28z"})
MINIM_PUNCTE = 10
PLAFON = 5.0  # o valoare mai mare nu e o retenție credibilă
LATIME, INALTIME = 300.0, 120.0  # sistemul de coordonate al graficului (viewBox)

Puncte = list[tuple[float, float]]


class CurbaRefuzata(ValueError):
    """Punctele primite nu au forma unei curbe de retenție."""


@dataclass(frozen=True)
class Rezumat:
    medie: float  # retenția medie pe tot clipul (aproximativ procentul mediu vizionat)
    dupa_hook: float  # retenția după primele 10% din clip
    la_final: float
    cadere_pozitie: float  # unde e cea mai mare cădere între două puncte vecine (poziția în clip)
    cadere_marime: float  # cât s-a pierdut acolo (0 dacă nu scade nicăieri)


def valideaza(puncte: Puncte) -> Puncte:
    """Punctele ordonate după poziție, sau `CurbaRefuzata`."""
    if len(puncte) < MINIM_PUNCTE:
        raise CurbaRefuzata(f"prea puține puncte ({len(puncte)}); platforma nu are încă date")
    ordonate = sorted((float(x), float(y)) for x, y in puncte)
    pozitii = [x for x, _ in ordonate]
    if pozitii[0] < 0.0 or pozitii[-1] > 1.0 or len(set(pozitii)) != len(pozitii):
        raise CurbaRefuzata("pozițiile trebuie să fie distincte, între 0 și 1")
    if any(y < 0.0 or y > PLAFON for _, y in ordonate):
        raise CurbaRefuzata(f"valorile trebuie să fie între 0 și {PLAFON}")
    return ordonate


def rezumat(puncte: Puncte) -> Rezumat:
    """Nucleu pur, pe o curbă validă."""
    p = valideaza(puncte)
    cadere_pozitie, cadere_marime = p[0][0], 0.0
    for (_, y0), (x1, y1) in itertools.pairwise(p):
        if y0 - y1 > cadere_marime:
            cadere_pozitie, cadere_marime = x1, y0 - y1
    dupa_hook = next((y for x, y in p if x >= 0.10), p[-1][1])
    return Rezumat(
        medie=round(sum(y for _, y in p) / len(p), 4),
        dupa_hook=round(dupa_hook, 4),
        la_final=round(p[-1][1], 4),
        cadere_pozitie=round(cadere_pozitie, 4),
        cadere_marime=round(cadere_marime, 4),
    )


def linie_svg(puncte: Puncte) -> tuple[str, float]:
    """Coordonatele liniei (`points` pentru `<polyline>`) într-un grafic `LATIME` × `INALTIME` și valoarea
    din vârful axei verticale (1.0, sau maximul curbei dacă trece de 1)."""
    p = valideaza(puncte)
    varf = max(1.0, max(y for _, y in p))
    coordonate = " ".join(f"{x * LATIME:.1f},{INALTIME - (y / varf) * INALTIME:.1f}" for x, y in p)
    return coordonate, varf


def salveaza(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    livrabil_id: uuid.UUID,
    canal: str,
    id_extern: str,
    interval: str,
    puncte: Puncte,
    acum: dt.datetime,
) -> None:
    """Curba validă înlocuiește curba veche a aceluiași clip."""
    valori = [[round(x, 4), round(y, 4)] for x, y in valideaza(puncte)]
    date = {"id_extern": id_extern[:300], "interval": interval, "puncte": valori, "citit_la": acum}
    db.execute(
        pg_insert(CurbaRetentie)
        .values(id=new_id(), tenant_id=tenant_id, livrabil_id=livrabil_id, canal=canal, **date)
        .on_conflict_do_update(constraint="curbe_retentie_unic", set_=date)
    )


def actualizeaza(
    tenant_id: uuid.UUID,
    livrabil_id: uuid.UUID,
    canal: str,
    id_extern: str,
    publicat_la: dt.datetime,
    interval: str,
    acum: dt.datetime,
) -> str:
    """Citește curba de la platformă și o ține. Întoarce `citita`, `fara_cititor`, `nu_acum` (intervalul nu
    are curbă), `fara_date` (platforma nu are încă destule puncte) sau `esuata`. Nu aruncă: curba e un
    adaos, nu are voie să strice citirea metricilor."""
    if interval not in INTERVALE_CU_CURBA:
        return "nu_acum"
    if not usa_metrici.are_retentie(canal):
        return "fara_cititor"
    try:
        puncte = usa_metrici.citeste_retentie(tenant_id, canal, id_extern, publicat_la.date(), acum.date())
    except motor.EroareMotor as exc:
        log.info("curbă de retenție necitită", extra={"canal": canal, "tip_eroare": type(exc).__name__})
        return "esuata"
    try:
        with sesiune_tenant(tenant_id) as db:
            salveaza(
                db, tenant_id=tenant_id, livrabil_id=livrabil_id, canal=canal, id_extern=id_extern,
                interval=interval, puncte=puncte, acum=acum,
            )  # fmt: skip
    except CurbaRefuzata as exc:
        log.info("curbă de retenție refuzată", extra={"canal": canal, "motiv": str(exc)[:120]})
        return "fara_date"
    return "citita"


def a_livrabilului(db: Session, livrabil_id: uuid.UUID, canal: str | None = None) -> CurbaRetentie | None:
    q = select(CurbaRetentie).where(CurbaRetentie.livrabil_id == livrabil_id)
    if canal is not None:
        q = q.where(CurbaRetentie.canal == canal)
    return db.execute(q.order_by(CurbaRetentie.citit_la.desc()).limit(1)).scalar_one_or_none()


def puncte(curba: CurbaRetentie) -> Puncte:
    return [(float(x), float(y)) for x, y in curba.puncte]


def numar(db: Session, tenant_id: uuid.UUID) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(CurbaRetentie).where(CurbaRetentie.tenant_id == tenant_id)
        ).scalar_one()
    )
