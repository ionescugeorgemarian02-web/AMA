"""Portalul clientului (F7, docs/19 §19.2): contul, onboardingul, Creierul, calendarul, aprobările,
materialele,
facturarea și datele, pentru utilizatorii de client (RLS pe clientul lor).

    from app import portal
    portal.inregistreaza(app)
    portal.cont.invita(db, tenant_id, "client@firma.ro")   # linkul de activare, pe email
"""

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app import finante
from app.finante.modele import Abonament
from app.portal import cont, date, progres
from app.portal.cont_web import router as router_cont
from app.portal.lucru_web import router as router_lucru
from app.portal.materiale_web import router as router_materiale
from app.portal.rapoarte_web import router as router_rapoarte
from app.portal.web import router


def inregistreaza(app: FastAPI) -> None:
    app.include_router(router)
    app.include_router(router_lucru)
    app.include_router(router_materiale)
    app.include_router(router_cont)
    app.include_router(router_rapoarte)


def _invita_dupa_plata(db: Session, a: Abonament) -> None:
    """19.3 pasul 1: după plată, clientul primește linkul de activare a contului."""
    cont.invita(db, a.tenant_id, a.email_facturare, motiv=f"plata:{a.id}")


finante.abonamente.inregistreaza_dupa_activare(_invita_dupa_plata)


__all__ = ["cont", "date", "inregistreaza", "progres", "router"]
