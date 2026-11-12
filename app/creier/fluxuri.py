"""Fluxul durabil al indexării (F4.3): `creier.indexeaza_sursa(tenant_id, sursa_id)` pe coada `io`.

Primește doar identificatori. Pasul de pregătire taie documentele în pasaje; pașii de vectorizare lucrează în
loturi.
Când gateway-ul spune `Amanat` (niciun model de vectori activ, server căzut) fluxul își reprogramează munca
pentru
momentul cerut (`gateway.reprogrameaza`) și se încheie; la reluare continuă cu ce a rămas, fiindcă pasajele
fără vector
sunt chiar lista de lucru.
"""

import datetime as dt
import uuid

from app import cercetare, gateway
from app.creier import indexare
from app.db import sesiune_tenant
from app.logging import get_logger
from app.operare import motor
from app.operare.motor import Coada, Prioritate

log = get_logger("app.creier")
NUME_FLUX = "creier.indexeaza_sursa"
LOTURI_MAXIME = 500


@motor.pas(nume="creier.pregateste_pasaje", reincercari=1)
def _pregateste(tenant_id: str, sursa_id: str) -> str:
    with sesiune_tenant(uuid.UUID(tenant_id)) as db:
        return f"pasaje_noi={indexare.pregateste_sursa(db, uuid.UUID(sursa_id))}"


@motor.pas(nume="creier.lot_vectori", reincercari=1)
def _lot(tenant_id: str, sursa_id: str) -> str:
    """`continua`, `gata` sau `amanat:<moment ISO>` (nu ridică `Amanat`: fluxul îl tratează singur)."""
    try:
        n = indexare.vectorizeaza_lot(uuid.UUID(tenant_id), uuid.UUID(sursa_id))
    except gateway.Amanat as amanat:
        return f"amanat:{amanat.pana_la.isoformat()}"
    return "continua" if n else "gata"


@motor.flux(NUME_FLUX, timp_maxim_sec=900)
def indexeaza_sursa(tenant_id: str, sursa_id: str) -> str:
    _pregateste(tenant_id, sursa_id)
    for _ in range(LOTURI_MAXIME):
        r = _lot(tenant_id, sursa_id)
        if r == "gata":
            return "gata"
        if r.startswith("amanat:"):
            pana = dt.datetime.fromisoformat(r.split(":", 1)[1])
            gateway.reprogrameaza(
                gateway.Amanat(pana, "vectori"), indexeaza_sursa, tenant_id, sursa_id,
                cheie=f"indexare:{sursa_id}:reluare", coada=Coada.IO, prioritate=Prioritate.P3,
            )  # fmt: skip
            return "amanat"
    return "partial"


def trimite(tenant_id: uuid.UUID, sursa_id: uuid.UUID, *, cheie: str) -> str:
    """Pune indexarea în coadă. Aceeași `cheie` (`indexare:<colectare_id>`), același job."""
    return motor.trimite(
        indexeaza_sursa, str(tenant_id), str(sursa_id), coada=Coada.IO, prioritate=Prioritate.P3, cheie=cheie
    )


def trimite_reindexarea(tenant_id: uuid.UUID, *, cheie: str) -> list[str]:
    """După schimbarea modelului: câte o indexare pentru fiecare sursă cu pasaje de re-vectorizat."""
    with sesiune_tenant(tenant_id) as db:
        surse = indexare.surse_de_vectorizat(db, tenant_id)
    return [trimite(tenant_id, s, cheie=f"{cheie}:{s}") for s in surse]


def _dupa_colectare(tenant_id: uuid.UUID, sursa_id: uuid.UUID, colectare_id: uuid.UUID) -> None:
    trimite(tenant_id, sursa_id, cheie=f"indexare:{colectare_id}")


def activeaza_indexarea_dupa_colectare() -> None:
    """Fiecare colectare terminată pornește indexarea sursei ei (apelat de worker la pornire)."""
    cercetare.dupa_colectare(_dupa_colectare)
