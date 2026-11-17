"""CRM-ul agenției (F12): firme, contacte, lead-uri, consimțământ. Intrarea: `registru.primeste`."""

from app.crm import registru
from app.crm.modele import Activitate, Consimtamant, Contact, Firma, LeadCrm, Sarcina
from app.crm.registru import CrmRefuzat

__all__ = ["Activitate", "Consimtamant", "Contact", "CrmRefuzat", "Firma", "LeadCrm", "Sarcina", "registru"]
