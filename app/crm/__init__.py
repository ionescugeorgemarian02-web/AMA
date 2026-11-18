"""CRM-ul agenției (F12): firme, contacte, lead-uri, consimțământ. Intrarea: `registru.primeste`.

Secvența de după audit: `secventa`; scorul: `calificare`; emailul comercial: `email.trimite`."""

from app.crm import calificare, conturi_tinta, inbox, oferte, programari, raspunsuri, registru, secventa
from app.crm.modele import Activitate, Consimtamant, Contact, Firma, LeadCrm, Oferta, Sarcina
from app.crm.registru import CrmRefuzat

__all__ = [
    "Activitate",
    "Consimtamant",
    "Contact",
    "CrmRefuzat",
    "Firma",
    "LeadCrm",
    "Oferta",
    "Sarcina",
    "calificare",
    "conturi_tinta",
    "inbox",
    "oferte",
    "programari",
    "raspunsuri",
    "registru",
    "secventa",
]
