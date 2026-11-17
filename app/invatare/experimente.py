"""Registrul de experimente (F11.4, K7, docs/11 §11.2, §11.6): un test simplu între două variante, cu
ipoteza, indicatorul și regula de oprire declarate DINAINTE și un rezultat calculat pe reguli.

- **Declararea** (`declara`): ipoteza în cuvinte, dimensiunea (tipar de hook, slot, format, canal), cele două
  variante, indicatorul (recompensa din F10.3), minimul de postări pe variantă, pragul de diferență și durata
  maximă. După creare, acestea nu se mai pot schimba (declanșator în bază). Un singur experiment în curs pe
  client și dimensiune (11.6: o schimbare o dată).
- **Datele**: postările clientului publicate după pornire, cu recompensa de tipul declarat și cu una dintre
  cele două variante. Nimic dinaintea pornirii nu intră.
- **Regula de oprire** (`verdict`, nucleu pur):
  - ambele variante au atins minimul → se încheie: câștigă varianta cu media mai mare DOAR dacă diferența
    relativă trece pragul declarat ȘI diferența e semnificativă (testul Welch, aproximație normală,
    |z| ≥ 1,96); altfel „fără diferență”;
  - durata maximă a trecut fără minim → „neconcludent” (nu se trage o concluzie din date puține);
  - altfel experimentul continuă.
- Aproximația normală e grosieră la eșantioane mici; de aceea minimul pe variantă se declară, iar rezultatul
  ține cifrele brute. Testele formale cu putere statistică sunt treapta N7 (F14).
"""

import datetime as dt
import math
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analiza import EtichetePostare, etichete
from app.db import sesiune_agentie, sesiune_tenant
from app.invatare.modele import Experiment
from app.logging import get_logger
from app.operare import audit, motor

log = get_logger("app.invatare.experimente")
NUME = "invatare.experimente"
Z_SEMNIFICATIV = 1.96
DIMENSIUNI = ("tipar_hook", "slot", "format", "canal")
ETICHETE_CONCLUZIE = {
    "castiga_a": "câștigă varianta A",
    "castiga_b": "câștigă varianta B",
    "fara_diferenta": "fără diferență",
    "neconcludent": "neconcludent (date prea puține)",
}


class ExperimentRefuzat(ValueError):
    pass


def _medie(x: list[float]) -> float:
    return sum(x) / len(x)


def _varianta(x: list[float]) -> float:
    m = _medie(x)
    return sum((v - m) ** 2 for v in x) / (len(x) - 1) if len(x) > 1 else 0.0


def verdict(
    a: list[float], b: list[float], *, minim: int, prag: float, expirat: bool
) -> tuple[str | None, dict[str, Any]]:
    """Nucleu pur. Întoarce (concluzia sau `None` dacă experimentul continuă, cifrele)."""
    cifre: dict[str, Any] = {
        "n_a": len(a),
        "n_b": len(b),
        "medie_a": round(_medie(a), 4) if a else None,
        "medie_b": round(_medie(b), 4) if b else None,
    }
    if len(a) < minim or len(b) < minim:
        return ("neconcludent" if expirat else None), cifre
    ma, mb = _medie(a), _medie(b)
    eroare = math.sqrt(_varianta(a) / len(a) + _varianta(b) / len(b))
    z = (ma - mb) / eroare if eroare > 0 else (0.0 if ma == mb else math.copysign(math.inf, ma - mb))
    baza = min(ma, mb)
    relativa = abs(ma - mb) / baza if baza > 0 else (math.inf if ma != mb else 0.0)
    cifre |= {
        "z": None if math.isinf(z) else round(z, 2),
        "diferenta_relativa": None if math.isinf(relativa) else round(relativa, 4),
    }
    if relativa >= prag and abs(z) >= Z_SEMNIFICATIV:
        return ("castiga_a" if ma > mb else "castiga_b"), cifre
    return "fara_diferenta", cifre


def declara(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    ipoteza: str,
    dimensiune: str,
    varianta_a: str,
    varianta_b: str,
    indicator: str = "interactiuni_pe_afisari",
    minim_pe_varianta: int = 10,
    prag_diferenta: float = 0.2,
    durata_maxima_zile: int = 60,
    utilizator_id: uuid.UUID | None,
    acum: dt.datetime | None = None,
) -> Experiment:
    ipoteza, a, b = ipoteza.strip(), varianta_a.strip(), varianta_b.strip()
    if dimensiune not in DIMENSIUNI:
        raise ExperimentRefuzat("dimensiune necunoscută")
    if len(ipoteza) < 10:
        raise ExperimentRefuzat("scrie ipoteza în cuvinte (cel puțin 10 caractere)")
    if not a or not b or a == b:
        raise ExperimentRefuzat("un experiment compară două variante diferite")
    if minim_pe_varianta < 2 or prag_diferenta <= 0 or durata_maxima_zile < 1:
        raise ExperimentRefuzat("regula de oprire nu e validă")
    in_curs = db.execute(
        select(Experiment.id).where(
            Experiment.tenant_id == tenant_id,
            Experiment.dimensiune == dimensiune,
            Experiment.stare == "in_curs",
        )
    ).first()
    if in_curs is not None:
        raise ExperimentRefuzat("există deja un experiment în curs pe această dimensiune: o schimbare o dată")
    e = Experiment(
        tenant_id=tenant_id,
        ipoteza=ipoteza[:400],
        dimensiune=dimensiune,
        varianta_a=a[:80],
        varianta_b=b[:80],
        indicator=indicator,
        minim_pe_varianta=minim_pe_varianta,
        prag_diferenta=prag_diferenta,
        durata_maxima_zile=durata_maxima_zile,
        inceput_la=acum or dt.datetime.now(dt.UTC),
        creat_de=utilizator_id,
    )
    db.add(e)
    db.flush()
    audit.record(
        db, "experiment.declarat", obiect_tip="experiment", obiect_id=e.id, tenant_id=tenant_id,
        utilizator_id=utilizator_id, detalii={"dimensiune": dimensiune, "minim": minim_pe_varianta},
    )  # fmt: skip
    return e


def _valoare(r: EtichetePostare, dimensiune: str) -> str:
    if dimensiune == "slot":
        return etichete.eticheta_slot(r.zi_saptamana, r.ora)
    return str(getattr(r, dimensiune) or "")


def _date(db: Session, e: Experiment) -> tuple[list[float], list[float]]:
    a: list[float] = []
    b: list[float] = []
    for r in db.execute(
        select(EtichetePostare).where(
            EtichetePostare.tenant_id == e.tenant_id,
            EtichetePostare.publicat_la >= e.inceput_la,
            EtichetePostare.recompensa.is_not(None),
            EtichetePostare.recompensa_tip == e.indicator,
        )
    ).scalars():
        v = _valoare(r, e.dimensiune)
        if v == e.varianta_a:
            a.append(float(r.recompensa or 0.0))
        elif v == e.varianta_b:
            b.append(float(r.recompensa or 0.0))
    return a, b


def evalueaza(db: Session, experiment_id: uuid.UUID, *, acum: dt.datetime | None = None) -> Experiment:
    """Aplică regula de oprire declarată. Un experiment încheiat rămâne cum e."""
    acum = acum or dt.datetime.now(dt.UTC)
    e = db.execute(
        select(Experiment).where(Experiment.id == experiment_id).with_for_update()
    ).scalar_one_or_none()
    if e is None:
        raise ExperimentRefuzat("experimentul nu există")
    if e.stare != "in_curs":
        return e
    a, b = _date(db, e)
    expirat = acum >= e.inceput_la + dt.timedelta(days=e.durata_maxima_zile)
    concluzie, cifre = verdict(a, b, minim=e.minim_pe_varianta, prag=e.prag_diferenta, expirat=expirat)
    e.rezultat = cifre
    if concluzie is not None:
        e.stare, e.concluzie, e.incheiat_la = "incheiat", concluzie, acum
        audit.record(
            db, "experiment.incheiat", obiect_tip="experiment", obiect_id=e.id, tenant_id=e.tenant_id,
            actor_tip="sistem", detalii={"concluzie": concluzie, "n_a": len(a), "n_b": len(b)},
        )  # fmt: skip
    db.flush()
    return e


def opreste(db: Session, experiment_id: uuid.UUID, *, utilizator_id: uuid.UUID, motiv: str) -> Experiment:
    e = db.execute(
        select(Experiment).where(Experiment.id == experiment_id).with_for_update()
    ).scalar_one_or_none()
    if e is None or e.stare != "in_curs":
        raise ExperimentRefuzat("doar un experiment în curs se poate opri")
    if len(motiv.strip()) < 3:
        raise ExperimentRefuzat("scrie de ce oprești experimentul")
    e.stare, e.motiv, e.incheiat_la = "oprit", motiv.strip()[:300], dt.datetime.now(dt.UTC)
    db.flush()
    audit.record(
        db, "experiment.oprit", obiect_tip="experiment", obiect_id=e.id, tenant_id=e.tenant_id,
        utilizator_id=utilizator_id, detalii={"motiv": motiv.strip()[:120]},
    )  # fmt: skip
    return e


def ale_clientului(db: Session, tenant_id: uuid.UUID | None = None, *, limita: int = 100) -> list[Experiment]:
    q = select(Experiment).order_by(Experiment.inceput_la.desc()).limit(limita)
    if tenant_id is not None:
        q = q.where(Experiment.tenant_id == tenant_id)
    return list(db.execute(q).scalars())


def ruleaza(acum: dt.datetime | None = None) -> int:
    """Evaluarea zilnică a experimentelor în curs, pe clientul fiecăruia. Întoarce câte s-au încheiat."""
    with sesiune_agentie() as db:
        in_curs = db.execute(
            select(Experiment.tenant_id, Experiment.id).where(Experiment.stare == "in_curs")
        ).all()
    incheiate = 0
    for tenant_id, eid in in_curs:
        try:
            with sesiune_tenant(tenant_id) as db:
                incheiate += evalueaza(db, eid, acum=acum).stare == "incheiat"
        except Exception as exc:
            log.warning("experiment neevaluat", extra={"tip_eroare": type(exc).__name__})
    return incheiate


@motor.pas("invatare.pas_experimente")
def _pas() -> str:
    return str(ruleaza())


@motor.flux(NUME)
def flux(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME, "40 6 * * *", flux)


declara_programari()
