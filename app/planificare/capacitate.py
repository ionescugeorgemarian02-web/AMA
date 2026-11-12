"""Planificatorul de capacitate (A4, tip D, docs/05): compară munca planificată a zilei cu cotele și cu
timpul de CPU și amână ce nu încape, după termen și prioritate (regulile: `reguli`).

Cum merge, la fiecare rulare (zilnic, 04:55 ora României, și la cerere):
1. livrabilele `planificat` ale căror termene intră în orizont (14 zile) și care nu sunt deja amânate
   dincolo de ziua de azi;
2. costul fiecăruia, din `planificare_costuri` (date editabile, estimări nemăsurate);
3. capacitatea: pe fiecare profil, cererile și tokenii care mai încap azi în cotele modelelor din lanț
   (`gateway.situatie`), iar pentru CPU, culoarele grele × minutele rămase din zi × factorul de utilizare;
4. amânarea: `productie.amana` pune `nu_inainte_de` = începutul zilei următoare; `productie.muta` refuză
   pornirea până atunci;
5. decizia se scrie (`planificare_planuri`, `planificare_decizii`) și, dacă s-a amânat ceva sau planul
   rămâne peste capacitate, pleacă o alertă „important” care spune ce nu a încăput.
Rularea repetată în aceeași zi este sigură: ce a fost amânat nu mai intră în planul de azi, iar planul
zilei se rescrie.
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import gateway, productie
from app.config import get_settings
from app.db import sesiune_agentie
from app.logging import get_logger
from app.operare import notificari
from app.planificare import reguli
from app.planificare.reguli import Capacitate, Cost, Decizie, Element, Rezultat

log = get_logger("app.planificare")
COSTUL_IMPLICIT = "_implicit"
PLAFON_ALERTA = 3  # axe numite în text


@dataclass(frozen=True)
class Plan:
    zi: dt.date
    rezultat: Rezultat
    capacitate: Capacitate
    amanate: tuple[uuid.UUID, ...]
    protejate: tuple[uuid.UUID, ...]
    nu_inainte_de: dt.datetime  # până când s-au amânat livrabilele
    alerta: str = ""

    @property
    def peste_capacitate(self) -> bool:
        return bool(self.rezultat.peste_capacitate)


def sfarsit_zi(acum: dt.datetime) -> dt.datetime:
    zi = acum.astimezone(dt.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return zi + dt.timedelta(days=1)


def costuri(db: Session) -> dict[str, Cost]:
    cost: dict[str, Cost] = {}
    for tip, profiluri, cpu in db.execute(text("SELECT tip, profiluri, minute_cpu FROM planificare_costuri")):
        cost[tip] = Cost(profiluri, float(cpu))
    return cost


def capacitate_azi(db: Session, profiluri: Sequence[str], acum: dt.datetime) -> Capacitate:
    s = get_settings()
    minute_ramase = (sfarsit_zi(acum) - acum).total_seconds() / 60
    apeluri: dict[str, int | None] = {}
    tokeni: dict[str, int | None] = {}
    for p in profiluri:
        apeluri[p], tokeni[p] = gateway.situatie.capacitate_profil(db, p, acum)
    return Capacitate(apeluri, tokeni, round(s.culoare_greu * minute_ramase * s.planificare_cpu_factor, 2))


def elemente_de_planificat(
    db: Session, acum: dt.datetime, clienti: Sequence[uuid.UUID] | None, cost: dict[str, Cost]
) -> list[Element]:
    s = get_settings()
    orizont = acum + dt.timedelta(days=s.planificare_orizont_zile)
    q = (
        "SELECT id, tenant_id, tip, termen_la FROM livrabile WHERE stare = 'planificat' "
        "AND (nu_inainte_de IS NULL OR nu_inainte_de < :sfarsit) "
        "AND (termen_la IS NULL OR termen_la <= :orizont)"
    )
    params: dict[str, object] = {"sfarsit": sfarsit_zi(acum), "orizont": orizont}
    if clienti is not None:
        q += " AND tenant_id = ANY(:clienti)"
        params["clienti"] = list(clienti)
    q += " ORDER BY id"
    return [
        Element(r[0], r[1], r[2], r[3], cost.get(r[2], cost.get(COSTUL_IMPLICIT, Cost())))
        for r in db.execute(text(q), params)
    ]


def _eticheta(axa: reguli.Axa) -> str:
    tip, profil = axa
    return "CPU greu (minute)" if tip == "cpu" else f"{'apeluri' if tip == 'apeluri' else 'tokeni'} {profil}"


def _alerta(plan_rez: Rezultat, cap: Capacitate, n_amanate: int, n_protejate: int) -> str:
    parti = []
    if n_amanate:
        parti.append(
            f"{n_amanate} livrabile nu au încăput în cotele zilei și au fost amânate pentru mâine "
            "(termenele cele mai îndepărtate)"
        )
    if plan_rez.peste_capacitate:
        parti.append(
            f"{n_protejate} cu termen apropiat rămân neatinse, dar planul depășește capacitatea la: "
            + ", ".join(_eticheta(a) for a in plan_rez.peste_capacitate[:PLAFON_ALERTA])
        )
    if plan_rez.depasiri:
        detalii = []
        for a in plan_rez.depasiri[:PLAFON_ALERTA]:
            limita = cap.limita(a)
            if limita is None:
                detalii.append(_eticheta(a))
            else:
                detalii.append(f"{_eticheta(a)}: cerut {plan_rez.cerere[a]:g}, disponibil {limita:g}")
        parti.append("axe depășite — " + "; ".join(detalii))
    return ". ".join(parti)[:900]


def planifica(
    *,
    acum: dt.datetime | None = None,
    clienti: Sequence[uuid.UUID] | None = None,
    anunta: bool = True,
) -> Plan:
    """Planul zilei de azi: citește, decide, amână, scrie, anunță. `clienti` restrânge planul (probe, un
    singur client)."""
    acum = acum or dt.datetime.now(dt.UTC)
    s = get_settings()
    prag = dt.timedelta(hours=s.planificare_termen_apropiat_ore)
    pana_la = sfarsit_zi(acum)
    with sesiune_agentie() as db:
        cost = costuri(db)
        elemente = elemente_de_planificat(db, acum, clienti, cost)
        profiluri = sorted({p for e in elemente for p in e.cost.profiluri})
        cap = capacitate_azi(db, profiluri, acum)
        rez = reguli.planifica(elemente, cap, acum, prag_apropiat=prag)
        amanate: list[uuid.UUID] = []
        for v in rez.cu_decizia(Decizie.AMANAT):
            try:
                productie.amana(db, v.element.id, pana_la, motiv=v.motiv)
                amanate.append(v.element.id)
            except productie.AmanareNepermisa as exc:  # ex.: termenul e înainte de mâine: rămâne
                log.warning(
                    "amânare refuzată", extra={"livrabil": str(v.element.id), "motiv": str(exc)[:100]}
                )
        protejate = [v.element.id for v in rez.cu_decizia(Decizie.PROTEJAT)]
        alerta = _alerta(rez, cap, len(amanate), len(protejate))
        _scrie(db, acum.date(), rez, cap, set(amanate), pana_la, alerta)
    plan = Plan(acum.date(), rez, cap, tuple(amanate), tuple(protejate), pana_la, alerta)
    if anunta and alerta and (amanate or rez.peste_capacitate):
        _anunta(len(amanate), alerta)
    return plan


def _scrie(
    db: Session,
    zi: dt.date,
    rez: Rezultat,
    cap: Capacitate,
    amanate: set[uuid.UUID],
    pana_la: dt.datetime,
    alerta: str,
) -> None:
    import json

    cerere = {f"{t}:{p}": n for (t, p), n in rez.cerere.items()}
    capacitate = {f"{t}:{p}": cap.limita((t, p)) for (t, p) in rez.cerere}
    pastrate = sum(1 for v in rez.verdicte if v.element.id not in amanate)
    db.execute(
        text(
            "INSERT INTO planificare_planuri (zi, calculat_la, livrabile, pastrate, amanate, "
            "protejate_peste_capacitate, cerere, capacitate, alerta) VALUES (:z, now(), :l, :p, :a, :pc, "
            "CAST(:c AS jsonb), CAST(:k AS jsonb), :al) "
            "ON CONFLICT (zi) DO UPDATE SET calculat_la = now(), livrabile = :l, pastrate = :p, "
            "amanate = :a, "
            "protejate_peste_capacitate = :pc, cerere = CAST(:c AS jsonb), capacitate = CAST(:k AS jsonb), "
            "alerta = :al"
        ),
        {"z": zi, "l": len(rez.verdicte), "p": pastrate, "a": len(amanate), "pc": bool(rez.peste_capacitate),
         "c": json.dumps(cerere), "k": json.dumps(capacitate), "al": alerta},
    )  # fmt: skip
    for v in rez.verdicte:
        e = v.element
        amanat = e.id in amanate
        db.execute(
            text(
                "INSERT INTO planificare_decizii (zi, livrabil_id, tenant_id, tip, decizie, prioritate, "
                "termen_la, nu_inainte_de, motiv) VALUES (:z, :i, :t, :tip, :d, :pr, :te, :nu, :m) "
                "ON CONFLICT (zi, livrabil_id) DO UPDATE SET decizie = :d, prioritate = :pr, "
                "nu_inainte_de = :nu, motiv = :m"
            ),
            {"z": zi, "i": e.id, "t": e.tenant_id, "tip": e.tip, "d": Decizie.AMANAT.value if amanat else
             (Decizie.PROTEJAT.value if v.decizie is Decizie.PROTEJAT else Decizie.PASTRAT.value),
             "pr": v.prioritate.name, "te": e.termen_la, "nu": pana_la if amanat else None, "m": v.motiv},
        )  # fmt: skip


def _anunta(n_amanate: int, alerta: str) -> None:
    try:
        notificari.notifica(
            notificari.Nivel.IMPORTANT,
            f"Capacitate: {n_amanate} livrabile amânate"
            if n_amanate
            else "Capacitate: planul depășește cotele",
            alerta[:290],
            url="/productie",
        )
    except Exception as exc:  # o alertă care nu pleacă nu are voie să strice planul
        log.warning("alerta de capacitate nu a plecat", extra={"tip_eroare": type(exc).__name__})


def main() -> int:
    plan = planifica()
    print(f"{plan.zi}: {len(plan.rezultat.verdicte)} livrabile, {len(plan.amanate)} amânate. {plan.alerta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
