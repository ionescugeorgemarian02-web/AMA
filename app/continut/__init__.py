"""Producția de conținut text (F6, docs/13): strategul de conținut și calendarul (D3),
autorul de brief (D5),
hook-urile, postările și scripturile video (E1, E4, E2, E8), cu validarea și aprobarea lor,
adaptorul pe platformă (E10),
capturarea feedbackului (respingeri și editări → exemple în contextul sarcinilor următoare).

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
    # E10: aceeași idee, câte un livrabil nou pe canal, în limitele de lungime:
    rez = continut.adaptor.adapteaza(db, livrabil_id, ["instagram", "linkedin", "tiktok"])
"""

from app.continut import (
    adaptor,
    brief,
    calendar,
    editor,
    feedback,
    fluxuri,
    pipeline,
    proba,
    scriere,
    scripturi,
)
from app.continut.modele import Adaptare, Brief, Calendar, IntrareCalendar, VariantaHook

__all__ = [
    "Adaptare",
    "Brief",
    "Calendar",
    "IntrareCalendar",
    "VariantaHook",
    "adaptor",
    "brief",
    "calendar",
    "editor",
    "feedback",
    "fluxuri",
    "pipeline",
    "proba",
    "scriere",
    "scripturi",
]
