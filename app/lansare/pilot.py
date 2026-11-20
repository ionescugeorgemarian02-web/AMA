"""Modul pilot (F15.5, docs/25 §25.4 poarta 2, §25.6): trei clienți la L1, preț de pilot, feedback săptămânal.

- `inscrie`: clientul intră în pilot cu toate clasele de acțiuni la L1 (orice acțiune cere aprobarea lui)
  și cu prețul de pilot (dacă are abonament, suma lui devine prețul de pilot), cu audit.
- `feedback`: întâlnirea săptămânală de 20 de minute: satisfacția (1–5), minutele de om, fricțiunile.
- `raporteaza_incident`: un incident critic (o urmă `pilot / incident_critic`), cu retrogradarea autonomiei.
- `indicatori`: calculați din urme (`app/operare/urme`), nu declarați: **aprobarea din prima** = livrabilele a
  căror PRIMĂ decizie de aprobare (urma `aprobare / decizie:*`) a fost „aprobat”, din livrabilele decise în
  fereastră; **incidentele critice** = urmele `pilot / incident_critic` din fereastră.
- `raport_saptamanal`: pe fiecare client din pilot, săptămâna (luni–duminică) cu indicatorii, feedback-ul și
  starea porții: „trece” doar după `saptamani` săptămâni fără incident critic, cu aprobarea din prima > 85%.
"""

import datetime as dt
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.comert import atribuire
from app.lansare.modele import PilotClient, PilotFeedback, PilotRaport
from app.operare import audit, urme
from app.operare.urme import Urma

PRAG_APROBARE = 0.85  # docs/25 §25.4: „aprobare din prima peste 85%”
SAPTAMANI = 4  # docs/23 F15.5: „patru săptămâni fără incident critic”
MAX_CLIENTI = 3  # docs/25 §25.6: „trei clienți din nișa aleasă”


class PilotInvalid(ValueError):
    pass


def luni(zi: dt.date) -> dt.date:
    return zi - dt.timedelta(days=zi.weekday())


def _moment(zi: dt.date) -> dt.datetime:
    return dt.datetime.combine(zi, dt.time(), dt.UTC)


def inscrie(
    db: Session, tenant_id: uuid.UUID, *, pret_lunar_bani: int, utilizator_id: uuid.UUID, rol: str,
    inceput: dt.date | None = None, saptamani: int = SAPTAMANI, note: str = "",
) -> PilotClient:  # fmt: skip
    from app.finante.modele import Abonament
    from app.productie import Clasa, Nivel, autonomie

    activi = db.execute(
        select(func.count()).select_from(PilotClient).where(PilotClient.stare == "activ")
    ).scalar()
    if db.get(PilotClient, tenant_id) is None and int(activi or 0) >= MAX_CLIENTI:
        raise PilotInvalid(f"pilotul are deja {MAX_CLIENTI} clienți activi")
    if pret_lunar_bani < 0:
        raise PilotInvalid("prețul de pilot nu poate fi negativ")
    db.execute(
        pg_insert(PilotClient)
        .values(tenant_id=tenant_id, inceput=inceput or dt.datetime.now(dt.UTC).date(), saptamani=saptamani,
                pret_lunar_bani=pret_lunar_bani, note=note[:2000], creat_de=utilizator_id)
        .on_conflict_do_update(index_elements=["tenant_id"], set_={"pret_lunar_bani": pret_lunar_bani,
                               "stare": "activ", "note": note[:2000]})
    )  # fmt: skip
    for c in Clasa:
        autonomie.seteaza_nivel(
            db,
            tenant_id,
            c,
            Nivel.L1,
            utilizator_id=utilizator_id,
            rol=rol,
            motiv="Pilot: totul la L1 (25.6)",
        )
    ab = db.execute(select(Abonament).where(Abonament.tenant_id == tenant_id)).scalars().first()
    if ab is not None and ab.suma != pret_lunar_bani:
        ab.suma = pret_lunar_bani  # # NEVERIFICAT: suma la procesatorul real de plăți se schimbă la migrare
    audit.record(
        db, "pilot.inscris", obiect_tip="client", obiect_id=tenant_id, tenant_id=tenant_id,
        utilizator_id=utilizator_id, detalii={"pret_lunar_bani": pret_lunar_bani, "saptamani": saptamani},
    )  # fmt: skip
    db.flush()
    p = db.get(PilotClient, tenant_id)
    assert p is not None  # noqa: S101 — tocmai scris
    db.refresh(p)
    return p


def feedback(
    db: Session, tenant_id: uuid.UUID, *, zi: dt.date, satisfactie: int, minute_om: int, frictiuni: str,
    utilizator_id: uuid.UUID,
) -> None:  # fmt: skip
    if db.get(PilotClient, tenant_id) is None:
        raise PilotInvalid("clientul nu este în pilot")
    if not 1 <= satisfactie <= 5 or not 0 <= minute_om <= 10_000:
        raise PilotInvalid("satisfacția e 1–5, minutele 0–10 000")
    s = luni(zi)
    db.execute(
        pg_insert(PilotFeedback)
        .values(id=uuid.uuid4(), tenant_id=tenant_id, saptamana=s, satisfactie=satisfactie,
                minute_om=minute_om, frictiuni=frictiuni.strip()[:4000], creat_de=utilizator_id)
        .on_conflict_do_update(index_elements=["tenant_id", "saptamana"], set_={"satisfactie": satisfactie,
                               "minute_om": minute_om, "frictiuni": frictiuni.strip()[:4000]})
    )  # fmt: skip
    urme.inregistreaza(
        db, "pilot", "feedback", tenant_id=tenant_id, rezultat="info", obiect_tip="client",
        obiect_id=str(tenant_id), intrari={"saptamana": s.isoformat(), "satisfactie": satisfactie},
    )  # fmt: skip


def raporteaza_incident(
    db: Session, tenant_id: uuid.UUID, *, descriere: str, utilizator_id: uuid.UUID
) -> None:
    from app.productie import autonomie

    descriere = descriere.strip()
    if len(descriere) < 5:
        raise PilotInvalid("descrie incidentul (cel puțin 5 caractere)")
    urme.inregistreaza(
        db, "pilot", "incident_critic", tenant_id=tenant_id, rezultat="esec", cod="incident_critic",
        motiv=descriere[:300], actor=f"utilizator:{utilizator_id}", obiect_tip="client",
        obiect_id=str(tenant_id),
    )  # fmt: skip
    autonomie.retrogradeaza(db, tenant_id, motiv=f"Incident critic în pilot: {descriere}"[:300])


@dataclass(frozen=True)
class Indicatori:
    decise: int
    aprobate_din_prima: int
    incidente_critice: int
    minute_om: int
    satisfactie: float | None
    feedback_saptamani: int

    @property
    def rata_aprobare_din_prima(self) -> float | None:
        return round(self.aprobate_din_prima / self.decise, 4) if self.decise else None

    def ca_dict(self) -> dict[str, Any]:
        return asdict(self) | {"rata_aprobare_din_prima": self.rata_aprobare_din_prima}


def indicatori(db: Session, tenant_id: uuid.UUID, de_la: dt.date, pana_la: dt.date) -> Indicatori:
    """Indicatorii clientului în [de_la, pana_la) din urme (și minutele / satisfacția din feedback)."""
    a, b = _moment(de_la), _moment(pana_la)
    decizii = db.execute(
        select(Urma.obiect_id, Urma.rezultat, Urma.la)
        .where(Urma.tenant_id == tenant_id, Urma.componenta == "aprobare", Urma.actiune.like("decizie:%"),
               Urma.la < b)
        .order_by(Urma.la)
    ).all()  # fmt: skip
    prima: dict[str, tuple[str, dt.datetime]] = {}
    in_fereastra: set[str] = set()
    for obiect, rezultat, la in decizii:
        if obiect is None:
            continue
        prima.setdefault(obiect, (rezultat, la))
        if la >= a:
            in_fereastra.add(obiect)
    din_prima = sum(1 for o in in_fereastra if prima[o][0] == "ok")
    incidente = db.execute(
        select(func.count())
        .select_from(Urma)
        .where(Urma.tenant_id == tenant_id, Urma.la >= a, Urma.la < b, Urma.componenta == "pilot",
               Urma.actiune == "incident_critic")
    ).scalar_one()  # fmt: skip
    fb = db.execute(
        select(PilotFeedback).where(PilotFeedback.tenant_id == tenant_id,
                                    PilotFeedback.saptamana >= luni(de_la), PilotFeedback.saptamana < pana_la)
    ).scalars().all()  # fmt: skip
    return Indicatori(
        decise=len(in_fereastra),
        aprobate_din_prima=din_prima,
        incidente_critice=int(incidente),
        minute_om=sum(f.minute_om for f in fb),
        satisfactie=round(sum(f.satisfactie for f in fb) / len(fb), 2) if fb else None,
        feedback_saptamani=len(fb),
    )


def stare_poarta(db: Session, p: PilotClient, azi: dt.date) -> dict[str, Any]:
    """Poarta pilotului (F15.5): `saptamani` săptămâni încheiate, zero incidente critice, aprobarea din prima
    peste 85%."""
    capat = min(azi + dt.timedelta(days=1), p.inceput + dt.timedelta(weeks=p.saptamani))  # `azi` inclusiv
    total = indicatori(db, p.tenant_id, p.inceput, capat)
    saptamani_gata = max(0, (capat - p.inceput).days // 7)
    rata = total.rata_aprobare_din_prima
    motive = []
    if saptamani_gata < p.saptamani:
        motive.append(f"{saptamani_gata}/{p.saptamani} săptămâni încheiate")
    if total.incidente_critice:
        motive.append(f"{total.incidente_critice} incidente critice")
    if rata is None or rata <= PRAG_APROBARE:
        motive.append("aprobarea din prima " + ("nemăsurată" if rata is None else f"{rata:.0%}") + " (> 85%)")
    if total.feedback_saptamani < saptamani_gata:
        motive.append(f"feedback pe {total.feedback_saptamani} din {saptamani_gata} săptămâni")
    return {"trece": not motive, "motive": motive, "saptamani_gata": saptamani_gata, **total.ca_dict()}


def raport_saptamanal(db: Session, saptamana: dt.date) -> list[dict[str, Any]]:
    """Raportul săptămânii (luni–duminică) pentru fiecare client activ din pilot; se salvează (idempotent)."""
    s = luni(saptamana)
    out = []
    for p in db.execute(select(PilotClient).where(PilotClient.stare == "activ")).scalars():
        ind = indicatori(db, p.tenant_id, s, s + dt.timedelta(days=7))
        continut = {
            "saptamana": s.isoformat(),
            "saptamana_pilot": (s - luni(p.inceput)).days // 7 + 1,
            **ind.ca_dict(),
            "feedback_lipsa": ind.feedback_saptamani == 0,
            "comercial": atribuire.materiale(db, p.tenant_id, _moment(s), _moment(s + dt.timedelta(days=7))),
            "poarta": stare_poarta(db, p, s + dt.timedelta(days=6)),
        }
        db.execute(
            pg_insert(PilotRaport)
            .values(id=uuid.uuid4(), tenant_id=p.tenant_id, saptamana=s, continut=continut)
            .on_conflict_do_update(index_elements=["tenant_id", "saptamana"],
                                   set_={"continut": continut, "generat_la": func.now()})
        )  # fmt: skip
        out.append({"tenant_id": str(p.tenant_id), **continut})
    return out


def clienti(db: Session) -> list[PilotClient]:
    return list(db.execute(select(PilotClient).order_by(PilotClient.creat_la)).scalars())
