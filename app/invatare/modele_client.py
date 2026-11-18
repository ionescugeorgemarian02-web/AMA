"""Scorul de lead și riscul de plecare, ca modele (F14.5, N6, docs/11 §11.2): doar peste pragul de date și
folosite doar dacă bat regulile simple pe date trecute.

- **Lead-uri** (CRM-ul agenției, F12.1): un exemplu = un lead închis (`castigat` = 1, `pierdut` = 0), cu
  sursa, temeiul și numărul de note. Regula simplă (`scor_regula_lead`): puncte pe sursă + puncte pe note.
  Pragul: `PRAG_LEAD` lead-uri închise.
- **Plecare** (clienții agenției): un exemplu = fișa de risc a unui client la un moment dat (`DateRisc`,
  F10.4)
  și dacă a plecat în următoarele 60 de zile. Regula simplă = riscul din scorul de sănătate existent
  (`analiza.sanatate`: 1 − scor / 100). Pragul: `PRAG_PLECARE` fișe.
  # NECONECTAT: fișele de risc nu se păstrează încă în timp (scorul de sănătate se calculează pe loc), deci pe
  date reale numărul de exemple e 0 și modelul rămâne `sub_prag`; mecanismul e verificat pe date simulate.
- Comparația: AUC-ul modelului față de al regulii pe testul din urmă, cu intervalul bootstrap pereche;
  `valid` doar dacă marginea de jos trece de `predictiv.MARJA`. Altfel regula rămâne cea folosită.
"""

import dataclasses
import datetime as dt
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analiza import sanatate
from app.crm import Activitate, LeadCrm
from app.db import sesiune_agentie
from app.invatare import predictiv
from app.invatare.modele import ModelPredictiv
from app.logging import get_logger
from app.operare import motor

log = get_logger("app.invatare.modele_client")
NUME = "invatare.modele_client"

PRAG_LEAD = 300
PRAG_PLECARE = 200
PUNCTE_SURSA = {"recomandare": 40, "programare": 35, "formular_audit": 30, "inbox": 20,
                "formular_reclama": 15, "resursa": 10}  # fmt: skip


def scor_regula_lead(sursa: str, note: int) -> float:
    """Regula simplă de până acum, ca referință: sursa + implicarea (note), între 0 și 1."""
    return (PUNCTE_SURSA.get(sursa, 0) + min(30, 10 * note)) / 70


def exemplu_lead(sursa: str, temei: str, note: int, castigat: bool, moment: dt.datetime) -> predictiv.Exemplu:
    return predictiv.Exemplu({"sursa": sursa, "temei": temei, "note": float(note)}, int(castigat), moment,
                             scor_regula_lead(sursa, note))  # fmt: skip


def exemple_lead(db: Session) -> list[predictiv.Exemplu]:
    """Lead-urile închise din CRM, cu notele lor (citire, în sesiunea de agenție)."""
    note = (
        select(Activitate.lead_id, func.count().label("n"))
        .where(Activitate.tip == "nota")
        .group_by(Activitate.lead_id)
        .subquery()
    )
    randuri = db.execute(
        select(LeadCrm.sursa, LeadCrm.temei, LeadCrm.etapa, LeadCrm.actualizat_la, func.coalesce(note.c.n, 0))
        .outerjoin(note, note.c.lead_id == LeadCrm.id)
        .where(LeadCrm.etapa.in_(("castigat", "pierdut")))
    ).all()
    return [exemplu_lead(s, t, int(n), e == "castigat", la) for s, t, e, la, n in randuri]


def trasaturi_plecare(d: sanatate.DateRisc, acum: dt.datetime) -> dict[str, Any]:
    def zile(m: dt.datetime | None) -> float:
        return float((acum - m).days) if m else 999.0

    return {**{k: float(v) for k, v in dataclasses.asdict(d).items() if isinstance(v, int)},
            "zile_fara_portal": zile(d.ultima_autentificare), "vechime_zile": zile(d.client_de_la),
            "abonament": d.abonament_stare or "-"}  # fmt: skip


def scor_regula_plecare(d: sanatate.DateRisc, acum: dt.datetime) -> float:
    """Riscul după regulile scorului de sănătate (F10.4): 1 − scor / 100."""
    return 1 - sanatate.scor(sanatate.semnale(d, acum)) / 100


def exemplu_plecare(d: sanatate.DateRisc, acum: dt.datetime, a_plecat: bool) -> predictiv.Exemplu:
    return predictiv.Exemplu(trasaturi_plecare(d, acum), int(a_plecat), acum, scor_regula_plecare(d, acum))


def exemple_plecare(db: Session) -> list[predictiv.Exemplu]:
    """# NECONECTAT: istoricul fișelor de risc nu există încă (vezi docstring-ul modulului)."""
    return []


def ruleaza_lead(
    db: Session, *, exemple: list[predictiv.Exemplu] | None = None, prag: int = PRAG_LEAD,
    acum: dt.datetime | None = None,
) -> ModelPredictiv:  # fmt: skip
    ex = exemple_lead(db) if exemple is None else exemple
    return predictiv.ruleaza(db, tip="lead", exemple=ex, prag=prag, referinta="reguli", acum=acum)


def ruleaza_plecare(
    db: Session, *, exemple: list[predictiv.Exemplu] | None = None, prag: int = PRAG_PLECARE,
    acum: dt.datetime | None = None,
) -> ModelPredictiv:  # fmt: skip
    ex = exemple_plecare(db) if exemple is None else exemple
    return predictiv.ruleaza(db, tip="plecare", exemple=ex, prag=prag, referinta="reguli", acum=acum)


def scor_lead(db: Session, sursa: str, temei: str, note: int) -> tuple[float, str]:
    """Scorul unui lead deschis: modelul, dacă ultimul e `valid`; altfel regula simplă. Cu sursa scorului."""
    r = predictiv.ultimul(db, "lead")
    p = None if r is None else predictiv.prezice(r, {"sursa": sursa, "temei": temei, "note": float(note)})
    return (p, "model") if p is not None else (scor_regula_lead(sursa, note), "reguli")


def risc_plecare(db: Session, d: sanatate.DateRisc, acum: dt.datetime) -> tuple[float, str]:
    r = predictiv.ultimul(db, "plecare")
    p = None if r is None else predictiv.prezice(r, trasaturi_plecare(d, acum))
    return (p, "model") if p is not None else (scor_regula_plecare(d, acum), "reguli")


def ruleaza() -> int:
    """Jobul săptămânal: o încercare pe lead-uri și una pe plecare. Întoarce câte modele sunt valide."""
    valide = 0
    for f in (ruleaza_lead, ruleaza_plecare):
        try:
            with sesiune_agentie() as db:
                valide += f(db).stare == "valid"
        except Exception as exc:
            log.warning("model de client neantrenat", extra={"tip_eroare": type(exc).__name__})
    return valide


@motor.pas("invatare.pas_modele_client")
def _pas() -> str:
    return str(ruleaza())


@motor.flux(NUME)
def flux(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME, "50 3 * * 0", flux)


declara_programari()
