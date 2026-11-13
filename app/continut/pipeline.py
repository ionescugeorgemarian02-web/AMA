"""Lanțul unui livrabil din calendar (docs/13 §13.2): brief → scriere → validare (cu cel mult 2 reparații) →
aprobare.

Fiecare pas este o funcție cu tranzacția ei, care pornește de la starea din bază (reluarea după o cădere
găsește
livrabilul unde l-a lăsat). Fluxul durabil `continut.produ` le înfășoară ca pași (`fluxuri.py`); proba
accelerată
(F6.8) și testele le cheamă direct. `gateway.Amanat` iese neprins: nimic nu s-a mutat, apelantul
reprogramează.
"""

import uuid

from app import productie, validare
from app.continut import brief, scriere
from app.db import sesiune_tenant
from app.productie import Stare

MAXIM_PASI = 10  # plasă de siguranță; limitele reale (2 reparații, 12 predări) sunt ale producției


def stare(tenant_id: uuid.UUID, livrabil_id: uuid.UUID) -> Stare:
    with sesiune_tenant(tenant_id) as db:
        lv = productie.citeste(db, livrabil_id)
        if lv is None:
            raise productie.LivrabilInexistent(str(livrabil_id))
        return Stare(lv.stare)


def pas(tenant_id: uuid.UUID, livrabil_id: uuid.UUID) -> str:
    """Un pas din lanț, după starea curentă. Întoarce starea de după (sau `fara_autor`)."""
    s = stare(tenant_id, livrabil_id)
    with sesiune_tenant(tenant_id) as db:
        if s is Stare.PLANIFICAT:
            brief.scrie(db, livrabil_id)
        elif s in (Stare.BRIEFAT, Stare.IN_SCRIERE):
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
        if r == "fara_autor" or Stare(r) not in LUCRU:
            return r
        r = pas(tenant_id, livrabil_id)
    return r
