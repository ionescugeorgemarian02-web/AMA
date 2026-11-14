"""Modulul finanțe: planurile agenției (date), abonamentele și facturile (F7.6, docs/19 §19.5).

from app import finante
a, jeton = finante.abonamente.incepe(db, tenant_id, "crestere", email="facturi@firma.ro")
finante.abonamente.trateaza_webhook(corp, antet_semnatura)    # din /facturare/webhook
"""

from app.finante import abonamente, planuri
from app.finante.web import router

__all__ = ["abonamente", "planuri", "router"]
