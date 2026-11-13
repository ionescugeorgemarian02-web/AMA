"""Producția de conținut text (F6, docs/13): strategul de conținut și calendarul (D3).

Restul aplicației folosește doar ce se exportă aici:

    from app import continut

    # D3, prin modelul care amână (profilul `strategie`):
    job = continut.fluxuri.trimite_calendarul(tenant, om, inceput=data, cheie="calendar:…")
    # sloturile aprobate de un om devin livrabile `planificat`:
    livrabile = continut.calendar.aproba(db, calendar_id, utilizator_id=om)
"""

from app.continut import calendar, fluxuri
from app.continut.modele import Calendar, IntrareCalendar

__all__ = ["Calendar", "IntrareCalendar", "calendar", "fluxuri"]
