"""Producția de conținut text (F6, docs/13): strategul de conținut și calendarul (D3),
autorul de brief (D5).

Restul aplicației folosește doar ce se exportă aici:

    from app import continut

    # D3, prin modelul care amână (profilul `strategie`):
    job = continut.fluxuri.trimite_calendarul(tenant, om, inceput=data, cheie="calendar:…")
    # sloturile aprobate de un om devin livrabile `planificat`:
    livrabile = continut.calendar.aproba(db, calendar_id, utilizator_id=om)
    # D5: brieful fiecărui slot, cu faptele permise din pachetul de context:
    job = continut.fluxuri.trimite_briefurile(tenant, calendar_id, cheie="briefuri:…")
"""

from app.continut import brief, calendar, fluxuri
from app.continut.modele import Brief, Calendar, IntrareCalendar

__all__ = ["Brief", "Calendar", "IntrareCalendar", "brief", "calendar", "fluxuri"]
