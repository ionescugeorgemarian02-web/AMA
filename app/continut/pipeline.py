"""Lanțul unui livrabil din calendar (docs/13 §13.2): idee (F-idee) → brief → scriere → validare (cu cel
mult 2 reparații) → aprobare.

Fiecare pas este o funcție cu tranzacția ei, care pornește de la starea din bază (reluarea după o cădere
găsește
livrabilul unde l-a lăsat). Fluxul durabil `continut.produ` le înfășoară ca pași (`fluxuri.py`); proba
accelerată
(F6.8) și testele le cheamă direct. `gateway.Amanat` iese neprins: nimic nu s-a mutat, apelantul
reprogramează.
"""

import uuid

from app import productie, validare
from app.continut import brief, idei, scriere
from app.db import sesiune_tenant
from app.productie import Stare

MAXIM_PASI = 10  # plasă de siguranță; limitele reale (2 reparații, 12 predări) sunt ale producției
IDEE_LA_OM = "idee_la_om"  # niciun concept n-a trecut critica și validarea: alege omul (`idei.alege_manual`)
OPRIRI = frozenset({"fara_autor", IDEE_LA_OM})


def stare(tenant_id: uuid.UUID, livrabil_id: uuid.UUID) -> Stare:
    with sesiune_tenant(tenant_id) as db:
        lv = productie.citeste(db, livrabil_id)
        if lv is None:
            raise productie.LivrabilInexistent(str(livrabil_id))
        return Stare(lv.stare)


def idee_si_brief(tenant_id: uuid.UUID, livrabil_id: uuid.UUID) -> str | None:
    """Etapa de idee (tranzacția ei: conceptele rămân salvate și când merg la om), apoi brieful din conceptul
    ales. `IDEE_LA_OM` dacă ideea așteaptă omul; altfel `None`. Un brief existent nu mai cere idee."""
    with sesiune_tenant(tenant_id) as db:
        if brief.al_livrabilului(db, livrabil_id) is None:
            try:
                idei.pregateste(db, livrabil_id)
            except idei.IdeeLaOm:
                return IDEE_LA_OM  # ieșire normală din sesiune: conceptele și critica se salvează
    with sesiune_tenant(tenant_id) as db:
        brief.scrie(db, livrabil_id)
    return None


def pas(tenant_id: uuid.UUID, livrabil_id: uuid.UUID) -> str:
    """Un pas din lanț, după starea curentă. Întoarce starea de după (sau `fara_autor`, `idee_la_om`)."""
    s = stare(tenant_id, livrabil_id)
    if s is Stare.PLANIFICAT:
        return idee_si_brief(tenant_id, livrabil_id) or stare(tenant_id, livrabil_id).value
    with sesiune_tenant(tenant_id) as db:
        if s in (Stare.BRIEFAT, Stare.IN_SCRIERE):
            scriere.scrie(db, livrabil_id)
        elif s is Stare.IN_VALIDARE:
            validare.ruleaza_runda(db, livrabil_id)
        elif s is Stare.IN_REPARATIE:
            r = validare.ruleaza_repararea(db, livrabil_id)
            if r == "fara_autor":
                return r
        else:
            return s.value
    return stare(tenant_id, livrabil_id).value


LUCRU = frozenset({Stare.PLANIFICAT, Stare.BRIEFAT, Stare.IN_SCRIERE, Stare.IN_VALIDARE, Stare.IN_REPARATIE})


def produ(tenant_id: uuid.UUID, livrabil_id: uuid.UUID) -> str:
    """Duce livrabilul cât se poate de departe fără om: până la aprobare (sau validat, carantină,
    coada de erori)."""
    r = stare(tenant_id, livrabil_id).value
    for _ in range(MAXIM_PASI):
        if r in OPRIRI or Stare(r) not in LUCRU:
            return r
        r = pas(tenant_id, livrabil_id)
    return r
