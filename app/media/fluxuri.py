"""Randarea ca job durabil pe culoarele grele (F8.9, docs/14 §14.11, ADR-03): câte un job media pe culoar.

Fluxul primește doar identificatori (clientul și randarea pregătită de `montaj.pregateste`); pasul randează și
înregistrează rezultatul, cu timpul și memoria de vârf ale randării. O reluare după o cădere refuză dublura: o
randare deja `gata` sau `respinsa` nu se mai randează.
"""

import uuid

from app.db import sesiune_tenant
from app.media import montaj
from app.media.modele import Randare
from app.operare import motor
from app.operare.motor import Coada, Prioritate

NUME = "media.randeaza"


@motor.pas(nume="media.randeaza_pas", reincercari=1)
def _randeaza(tenant_id: str, randare_id: str) -> str:
    with sesiune_tenant(uuid.UUID(tenant_id)) as db:
        r = db.get(Randare, uuid.UUID(randare_id))
        if r is None:
            return "inexistenta"
        if r.stare != "in_lucru":
            return r.stare
        return montaj.executa(db, r).stare


@motor.flux(NUME, timp_maxim_sec=1800)
def randeaza(tenant_id: str, randare_id: str) -> str:
    return _randeaza(tenant_id, randare_id)


def trimite(tenant_id: uuid.UUID, randare_id: uuid.UUID, *, prioritate: Prioritate = Prioritate.P2) -> str:
    return motor.trimite(
        randeaza, str(tenant_id), str(randare_id), coada=Coada.GREU, prioritate=prioritate,
        cheie=f"randare:{randare_id}",
    )  # fmt: skip
