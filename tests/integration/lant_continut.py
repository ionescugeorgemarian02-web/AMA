"""Ajutor de test (F6): aduce brandul FICTIV „Cafeneaua Zorilor” până la o strategie pe 90 de zile APROBATĂ, prin serviciile
reale (lanțul Creierului din F4). Doar modelul este FALS (# SIMULAT)."""

import datetime as dt
import uuid
from typing import Any

from app import creier
from app.db import sesiune_tenant
from tests.integration.lant_onboarding import Lant, pana_la_insight
from tests.integration.test_onboarding_strategie import model_strategie, propune, strategie_db
from tests.onboarding_utile import ModelFals

INCEPUT = dt.date(2026, 12, 1)


def pana_la_strategie(tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals) -> Lant:
    """Brief, ghid, public, insight, fapte și strategie: toate aprobate de un om. Cere `executor`."""
    lant = pana_la_insight(tenant, om, modele)
    model_strategie(modele)
    propune(tenant, om, f"lant:strategie:{tenant}")
    iid, versiuni = strategie_db(tenant)
    with sesiune_tenant(tenant, om) as db:
        creier.aproba(db, iid, versiuni[-1].nr, utilizator_id=om)
    return lant


def calendar_aprobat(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, **kw: Any
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """Strategie aprobată, apoi un calendar pe 30 de zile propus (model FALS) și aprobat de un om."""
    from app import continut
    from app.operare import motor
    from tests.continut_utile import model_calendar

    pana_la_strategie(tenant, om, modele)
    model_calendar(modele, **kw)
    job = continut.fluxuri.trimite_calendarul(tenant, om, inceput=INCEPUT, cheie=f"lant:cal:{tenant}")
    assert motor.asteapta_flux(job, timeout_sec=60).stare.value == "terminat"
    with sesiune_tenant(tenant, om) as db:
        [cal] = continut.calendar.calendare(db, tenant)
        livrabile = continut.calendar.aproba(db, cal.id, utilizator_id=om)
    return cal.id, livrabile


def cu_briefuri(tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """Calendar aprobat și brieful fiecărui slot (D5, model FALS)."""
    from app import continut
    from app.operare import motor
    from tests.continut_utile import model_brief

    cal, livrabile = calendar_aprobat(tenant, om, modele)
    model_brief(modele)
    job = continut.fluxuri.trimite_briefurile(tenant, cal, cheie=f"lant:briefuri:{tenant}")
    assert motor.asteapta_flux(job, timeout_sec=120).stare.value == "terminat"
    return cal, livrabile
