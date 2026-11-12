"""# SIMULAT: fluxuri de probă pentru modelul local (F3.5), rulate de executorul din procesul testului.

Rezultatele se pun într-o listă din memorie (executorul rulează în același proces cu testul)."""

import threading
import uuid

from app import gateway
from app.db import sesiune_tenant
from app.operare import motor
from app.operare.motor import Prioritate
from tests.gateway_utile import Clasificare

REZULTATE: list[str] = []
VECTORI: list[list[list[float]]] = []
_lock = threading.Lock()


def reseteaza() -> None:
    with _lock:
        REZULTATE.clear()
        VECTORI.clear()


@motor.pas(nume="proba_local.clasifica_pas")
def _clasifica(tenant: str, prompt: str) -> str:
    t = uuid.UUID(tenant)
    try:
        with sesiune_tenant(t) as db:
            r = gateway.apeleaza(
                db, prompt=prompt, variabile={"text": "Livrarea a fost rapidă!"}, schema=Clasificare,
                tenant_id=t, componenta="proba.local", prioritate=Prioritate.P2,
            )  # fmt: skip
        rezultat = f"ok:{r.model}:{r.degradat}"
    except gateway.ApelRefuzat as exc:
        rezultat = f"refuzat:{exc.cod}"
    except gateway.Amanat:
        rezultat = "amanat"
    with _lock:
        REZULTATE.append(rezultat)
    return rezultat


@motor.flux("proba_local.clasifica")
def clasifica(tenant: str, prompt: str) -> str:
    return _clasifica(tenant, prompt)


@motor.pas(nume="proba_local.vectori_pas")
def _vectori(tenant: str) -> int:
    v = gateway.vectorizeaza(["prima propoziție", "a doua propoziție"], tenant_id=uuid.UUID(tenant))
    with _lock:
        VECTORI.append(v)
    return len(v)


@motor.flux("proba_local.vectori")
def vectori(tenant: str) -> int:
    return _vectori(tenant)
