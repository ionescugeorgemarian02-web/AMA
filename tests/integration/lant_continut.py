"""Ajutor de test (F6): aduce brandul FICTIV „Cafeneaua Zorilor” până la o strategie pe 90 de zile APROBATĂ, prin serviciile
reale (lanțul Creierului din F4). Doar modelul este FALS (# SIMULAT)."""

import uuid

from app import creier
from app.db import sesiune_tenant
from tests.integration.lant_onboarding import Lant, pana_la_insight
from tests.integration.test_onboarding_strategie import model_strategie, propune, strategie_db
from tests.onboarding_utile import ModelFals


def pana_la_strategie(tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals) -> Lant:
    """Brief, ghid, public, insight, fapte și strategie: toate aprobate de un om. Cere `executor`."""
    lant = pana_la_insight(tenant, om, modele)
    model_strategie(modele)
    propune(tenant, om, f"lant:strategie:{tenant}")
    iid, versiuni = strategie_db(tenant)
    with sesiune_tenant(tenant, om) as db:
        creier.aproba(db, iid, versiuni[-1].nr, utilizator_id=om)
    return lant
