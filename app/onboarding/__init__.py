"""Onboardingul clientului (docs/19 §19.3, docs/13 §13.8): interviul, brieful, ghidul de brand,
publicul, harta
pieței și prima strategie, toate scrise în Creierul de brand (versionat, aprobat de un om).

    from app import onboarding

    s = onboarding.sesiuni.deschide(db, tenant_id=t, utilizator_id=u)        # F4.4: interviu reluabil
    onboarding.sesiuni.raspunde(db, s.id, intrebare_id, "…", utilizator_id=u)  # clarificări generate de model
    onboarding.fluxuri.trimite_compunerea(t, s.id, u, cheie="brief:1")       # brief din răspunsuri +
    materiale
    onboarding.completare.trimite_spre_aprobare(db, s.id, utilizator_id=u)   # doar un brief complet
"""

from app.onboarding import brief, clarificare, completare, fluxuri, interviu, sesiuni
from app.onboarding.sesiuni import EroareOnboarding, SesiuneInchisa

__all__ = [
    "EroareOnboarding",
    "SesiuneInchisa",
    "brief",
    "clarificare",
    "completare",
    "fluxuri",
    "interviu",
    "sesiuni",
]
