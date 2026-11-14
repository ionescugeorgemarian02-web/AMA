"""Raportul lunar, prima formă (F7.8, docs/19 §19.6): livrabile și stare, încă fără metrici (F10).

O pagină, cu cele 7 secțiuni din 19.6; cele care cer metrici spun explicit că lipsesc (nu se inventează
cifre):
1. ce am livrat: publicate pe tip, față de pachet (planul abonamentului, dacă există);
2. ce a ieșit / 3. ce a mers / 4. ce nu a mers: fără metrici încă; din aprobări: rata de aprobare din prima și
   motivele de respingere;
5. ce am învățat despre public: fără metrici încă;
6. planul lunii următoare: sloturile din calendar;
7. ce avem nevoie de la client: aprobări în așteptare, întrebări deschise, pași de onboarding rămași.
Se generează din date (idempotent pe client + lună: o regenerare înlocuiește conținutul), se vede în
portal."""

import datetime as dt
import uuid
from collections import Counter
from typing import Any

from sqlalchemy import Date, DateTime, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app import continut, finante, productie, validare
from app.ids import new_id
from app.operare import audit
from app.productie import Stare

FARA_METRICI = (
    "Metricile de performanță vin cu analiza (F10); luna aceasta raportăm doar livrabilele și starea."
)
LIVRATE = {Stare.PUBLICAT.value, Stare.IN_MASURARE.value, Stare.INCHIS.value}


class Baza(DeclarativeBase):
    pass


class RaportLunar(Baza):
    __tablename__ = "rapoarte_lunare"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    luna: Mapped[dt.date] = mapped_column(Date)
    continut: Mapped[dict[str, Any]] = mapped_column(JSONB)
    generat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    stare: Mapped[str] = mapped_column(Text, default="generat")


def interval(luna: dt.date) -> tuple[dt.datetime, dt.datetime]:
    inceput = dt.datetime(luna.year, luna.month, 1, tzinfo=dt.UTC)
    urm = dt.datetime(luna.year + (luna.month == 12), luna.month % 12 + 1, 1, tzinfo=dt.UTC)
    return inceput, urm


def compune(db: Session, tenant_id: uuid.UUID, luna: dt.date) -> dict[str, Any]:
    """Nucleul raportului, din date (RLS pe client)."""
    de_la, pana_la = interval(luna)
    Liv = productie.Livrabil
    luna_lv = list(
        db.execute(
            select(Liv).where(
                Liv.tenant_id == tenant_id,
                func.coalesce(Liv.termen_la, Liv.creat_la) >= de_la,
                func.coalesce(Liv.termen_la, Liv.creat_la) < pana_la,
            )
        ).scalars()
    )
    livrate = Counter(lv.tip for lv in luna_lv if lv.stare in LIVRATE)
    in_lucru = Counter(lv.tip for lv in luna_lv if lv.stare not in LIVRATE)
    ab = finante.abonamente.al_clientului(db, tenant_id)
    pachet = finante.planuri.PLANURI[ab.plan].livrabile if ab and ab.plan in finante.planuri.PLANURI else {}
    tipuri = sorted(set(livrate) | set(in_lucru) | {t for t, n in pachet.items() if n and t != "raport"})
    livrat = [
        {
            "tip": t,
            "eticheta": finante.planuri.ETICHETE_LIVRABILE.get(t, t),
            "livrate": livrate.get(t, 0),
            "in_lucru": in_lucru.get(t, 0),
            "pachet": pachet.get(t),
        }
        for t in tipuri
    ]
    ids_luna = {lv.id for lv in luna_lv}  # deciziile pe livrabilele lunii (după slot), nu după ziua deciziei
    decizii = [
        a
        for a, lv in productie.aprobari.listeaza(db, doar_in_asteptare=False, limita=1000)
        if a.livrabil_id in ids_luna and a.decis_la is not None
    ]
    prima: dict[uuid.UUID, productie.Aprobare] = {}
    for a in sorted(decizii, key=lambda x: x.decis_la or de_la):
        prima.setdefault(a.livrabil_id, a)
    aprobate_din_prima = len([a for a in prima.values() if a.stare == "aprobat"])
    motive = Counter(
        productie.MOTIVE_RESPINGERE.get(a.motiv_cod or "", "altceva") for a in decizii if a.stare == "respins"
    )
    urm_de_la, urm_pana_la = interval(pana_la.date())
    sloturi: Counter[str] = Counter()
    for cal in continut.calendar.calendare(db, tenant_id, limita=3):
        if cal.stare == "aprobat":
            for i in continut.calendar.intrari(db, cal.id):
                if urm_de_la <= i.slot_la < urm_pana_la:
                    sloturi[i.tip] += 1
    nevoi = []
    n_aprobari = sum(1 for a, lv in productie.aprobari.listeaza(db, limita=1000) if lv.tenant_id == tenant_id)
    if n_aprobari:
        nevoi.append(f"{n_aprobari} materiale așteaptă aprobarea ta.")
    n_intrebari = sum(1 for q in validare.intrebari.deschise(db, limita=1000) if q.tenant_id == tenant_id)
    if n_intrebari:
        nevoi.append(f"{n_intrebari} întrebări despre fapte așteaptă un răspuns.")
    return {
        "luna": luna.strftime("%Y-%m"),
        "livrat": livrat,
        "rezultate": FARA_METRICI,
        "aprobari": {
            "decise": len(prima),
            "din_prima": aprobate_din_prima,
            "rata_din_prima": round(aprobate_din_prima / len(prima), 2) if prima else None,
            "motive_respingere": dict(motive),
        },
        "public": FARA_METRICI,
        "plan_luna_urmatoare": dict(sloturi),
        "nevoi": nevoi or ["Nimic acum."],
    }


def genereaza(
    db: Session, tenant_id: uuid.UUID, luna: dt.date, *, utilizator_id: uuid.UUID | None = None
) -> RaportLunar:
    luna = luna.replace(day=1)
    c = compune(db, tenant_id, luna)
    db.execute(
        pg_insert(RaportLunar)
        .values(id=new_id(), tenant_id=tenant_id, luna=luna, continut=c)
        .on_conflict_do_update(
            index_elements=["tenant_id", "luna"], set_={"continut": c, "generat_la": func.now()}
        )
    )
    r = db.execute(
        select(RaportLunar)
        .where(RaportLunar.tenant_id == tenant_id, RaportLunar.luna == luna)
        .execution_options(populate_existing=True)
    ).scalar_one()
    audit.record(
        db,
        "raport_lunar.generat",
        obiect_tip="raport",
        obiect_id=r.id,
        tenant_id=tenant_id,
        utilizator_id=utilizator_id,
        actor_tip="utilizator" if utilizator_id else "sistem",
        detalii={"luna": c["luna"]},
    )
    return r


def ale_clientului(db: Session, tenant_id: uuid.UUID) -> list[RaportLunar]:
    return list(
        db.execute(
            select(RaportLunar).where(RaportLunar.tenant_id == tenant_id).order_by(RaportLunar.luna.desc())
        ).scalars()
    )
