"""Fluxurile durabile ale producției de conținut (F6), pe coada `io`. Primesc doar identificatori; la
`gateway.Amanat`
(profil care amână, cotă epuizată) își reprogramează munca și se încheie. Nu degradează niciodată la un model
mai slab.
"""

import datetime as dt
import uuid

from app import creier, gateway
from app.continut import calendar
from app.db import sesiune_tenant
from app.logging import get_logger
from app.operare import motor
from app.operare.motor import Coada, Prioritate

log = get_logger("app.continut")

# --- calendarul (F6.1)

NUME_CALENDAR = "continut.calendar"


@motor.pas(nume="continut.calendar_pas", reincercari=1)
def _calendar(tenant_id: str, utilizator_id: str, inceput: str, zile: int) -> str:
    """`gata:<id>`, `amanat:<moment ISO>` sau `refuzat:<motiv>`."""
    try:
        with sesiune_tenant(uuid.UUID(tenant_id)) as db:
            cal = calendar.propune(
                db,
                tenant_id=uuid.UUID(tenant_id),
                utilizator_id=uuid.UUID(utilizator_id),
                inceput=dt.date.fromisoformat(inceput),
                zile=zile,
            )
            return f"gata:{cal.id}"
    except gateway.Amanat as amanat:
        return f"amanat:{amanat.pana_la.isoformat()}"
    except gateway.EroareGateway as exc:
        return f"refuzat:{type(exc).__name__}"
    except creier.RegulaCreier as exc:
        log.warning("calendarul nu s-a putut propune", extra={"motiv": str(exc)[:200]})
        return "refuzat:calendar_invalid"


@motor.flux(NUME_CALENDAR, timp_maxim_sec=900)
def propune_calendarul(tenant_id: str, utilizator_id: str, inceput: str, zile: int) -> str:
    r = _calendar(tenant_id, utilizator_id, inceput, zile)
    if r.startswith("amanat:"):
        gateway.reprogrameaza(
            gateway.Amanat(dt.datetime.fromisoformat(r.split(":", 1)[1]), "calendar"),
            propune_calendarul,
            tenant_id,
            utilizator_id,
            inceput,
            zile,
            cheie=f"calendar:{tenant_id}:{inceput}:reluare",
            coada=Coada.IO,
            prioritate=Prioritate.P1,
        )
        return "amanat"
    return r


def trimite_calendarul(
    tenant_id: uuid.UUID,
    utilizator_id: uuid.UUID,
    *,
    inceput: dt.date,
    zile: int = calendar.ZILE_IMPLICIT,
    cheie: str,
) -> str:
    return motor.trimite(
        propune_calendarul,
        str(tenant_id),
        str(utilizator_id),
        inceput.isoformat(),
        zile,
        coada=Coada.IO,
        prioritate=Prioritate.P1,
        cheie=cheie,
    )
