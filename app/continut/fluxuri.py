"""Fluxurile durabile ale producției de conținut (F6), pe coada `io`. Primesc doar identificatori; la
`gateway.Amanat`
(profil care amână, cotă epuizată) își reprogramează munca și se încheie. Nu degradează niciodată la un model
mai slab.
"""

import datetime as dt
import uuid

from app import creier, gateway
from app.continut import brief, calendar
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


# --- briefurile (F6.2)

NUME_BRIEFURI = "continut.briefuri"


@motor.pas(nume="continut.brief_pas", reincercari=1)
def _brief(tenant_id: str, livrabil_id: str) -> str:
    """`gata`, `amanat:<moment ISO>` sau `refuzat:<motiv>` pentru brieful unui livrabil."""
    try:
        with sesiune_tenant(uuid.UUID(tenant_id)) as db:
            brief.scrie(db, uuid.UUID(livrabil_id))
    except gateway.Amanat as amanat:
        return f"amanat:{amanat.pana_la.isoformat()}"
    except gateway.EroareGateway as exc:
        return f"refuzat:{type(exc).__name__}"
    except creier.RegulaCreier as exc:
        log.warning("brieful nu s-a putut scrie", extra={"motiv": str(exc)[:200]})
        return "refuzat:brief_invalid"
    return "gata"


@motor.flux(NUME_BRIEFURI, timp_maxim_sec=1800)
def scrie_briefurile(tenant_id: str, calendar_id: str) -> str:
    """Brieful fiecărui slot aprobat al calendarului care nu are încă unul. La prima amânare se reprogramează
    tot
    fluxul (briefurile scrise rămân: `brief.scrie` e idempotent)."""
    with sesiune_tenant(uuid.UUID(tenant_id)) as db:
        de_scris = [
            str(i.livrabil_id)
            for i in calendar.intrari(db, uuid.UUID(calendar_id))
            if i.livrabil_id is not None and brief.al_livrabilului(db, i.livrabil_id) is None
        ]
    refuzate = 0
    for lid in de_scris:
        r = _brief(tenant_id, lid)
        if r.startswith("amanat:"):
            gateway.reprogrameaza(
                gateway.Amanat(dt.datetime.fromisoformat(r.split(":", 1)[1]), "brief"),
                scrie_briefurile,
                tenant_id,
                calendar_id,
                cheie=f"briefuri:{calendar_id}:reluare:{lid}",
                coada=Coada.IO,
                prioritate=Prioritate.P2,
            )
            return "amanat"
        refuzate += r.startswith("refuzat:")
    return f"gata:{len(de_scris) - refuzate}:{refuzate}"


def trimite_briefurile(tenant_id: uuid.UUID, calendar_id: uuid.UUID, *, cheie: str) -> str:
    return motor.trimite(
        scrie_briefurile,
        str(tenant_id),
        str(calendar_id),
        coada=Coada.IO,
        prioritate=Prioritate.P2,
        cheie=cheie,
    )
