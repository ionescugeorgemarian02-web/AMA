"""Fluxurile durabile ale onboardingului (F4.4+): compunerea brieful, propunerea de ton și celelalte, pe coada
`io`. Primesc doar identificatori; la `gateway.Amanat` (profil care amână, cotă epuizată) își
reprogramează munca
pentru momentul cerut și se încheie, iar sesiunea arată `amanat_pana`. Nu degradează niciodată la un
model mai slab.
"""

import datetime as dt
import uuid

from sqlalchemy import update

from app import gateway
from app.db import sesiune_tenant
from app.onboarding import completare
from app.onboarding.modele import Sesiune
from app.operare import motor
from app.operare.motor import Coada, Prioritate

NUME_COMPUNERE = "onboarding.compune_brief"


def _amana(tenant_id: str, sesiune_id: str, pana: dt.datetime) -> None:
    with sesiune_tenant(uuid.UUID(tenant_id)) as db:
        db.execute(update(Sesiune).where(Sesiune.id == uuid.UUID(sesiune_id)).values(amanat_pana=pana))


@motor.pas(nume="onboarding.compune_brief_pas", reincercari=1)
def _compune(tenant_id: str, sesiune_id: str, utilizator_id: str) -> str:
    """`gata`, `amanat:<moment ISO>` sau `refuzat:<motiv>`."""
    try:
        with sesiune_tenant(uuid.UUID(tenant_id)) as db:
            completare.compune(db, uuid.UUID(sesiune_id), utilizator_id=uuid.UUID(utilizator_id))
    except gateway.Amanat as amanat:
        _amana(tenant_id, sesiune_id, amanat.pana_la)
        return f"amanat:{amanat.pana_la.isoformat()}"
    return "gata"


@motor.flux(NUME_COMPUNERE, timp_maxim_sec=600)
def compune_brief(tenant_id: str, sesiune_id: str, utilizator_id: str) -> str:
    r = _compune(tenant_id, sesiune_id, utilizator_id)
    if r.startswith("amanat:"):
        gateway.reprogrameaza(
            gateway.Amanat(dt.datetime.fromisoformat(r.split(":", 1)[1]), "brief"),
            compune_brief,
            tenant_id,
            sesiune_id,
            utilizator_id,
            cheie=f"brief:{sesiune_id}:reluare",
            coada=Coada.IO,
            prioritate=Prioritate.P2,
        )
        return "amanat"
    return r


def trimite_compunerea(
    tenant_id: uuid.UUID, sesiune_id: uuid.UUID, utilizator_id: uuid.UUID, *, cheie: str
) -> str:
    """Pune compunerea brieful în coadă (idempotent pe `cheie`). Sesiunea trece pe `compune`."""
    with sesiune_tenant(tenant_id) as db:
        db.execute(
            update(Sesiune)
            .where(Sesiune.id == sesiune_id, Sesiune.stare.in_(("interviu", "brief_gata", "compune")))
            .values(stare="compune", actualizat_la=dt.datetime.now(dt.UTC))
        )
    return motor.trimite(
        compune_brief, str(tenant_id), str(sesiune_id), str(utilizator_id), coada=Coada.IO,
        prioritate=Prioritate.P2, cheie=cheie,
    )  # fmt: skip
