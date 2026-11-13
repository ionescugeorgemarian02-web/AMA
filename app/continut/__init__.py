"""Producția de conținut text (F6, docs/13): strategul de conținut și calendarul (D3),
autorul de brief (D5),
hook-urile și postările (E1, E4, E8), cu validarea și aprobarea lor.

Restul aplicației folosește doar ce se exportă aici:

    from app import continut

    # D3, prin modelul care amână (profilul `strategie`):
    job = continut.fluxuri.trimite_calendarul(tenant, om, inceput=data, cheie="calendar:…")
    # sloturile aprobate de un om devin livrabile `planificat`:
    livrabile = continut.calendar.aproba(db, calendar_id, utilizator_id=om)
    # D5: brieful fiecărui slot, cu faptele permise din pachetul de context:
    job = continut.fluxuri.trimite_briefurile(tenant, calendar_id, cheie="briefuri:…")
    # un livrabil: brief → hook-uri → postare → editare → validare (≤ 2 reparații) → aprobare:
    job = continut.fluxuri.trimite_productia(tenant, livrabil_id, cheie="produ:…")
    stare = continut.pipeline.produ(tenant, livrabil_id)  # același lanț, sincron (proba, testele)
"""

from app.continut import brief, calendar, editor, fluxuri, pipeline, scriere
from app.continut.modele import Brief, Calendar, IntrareCalendar, VariantaHook

__all__ = [
    "Brief",
    "Calendar",
    "IntrareCalendar",
    "VariantaHook",
    "brief",
    "calendar",
    "editor",
    "fluxuri",
    "pipeline",
    "scriere",
]
