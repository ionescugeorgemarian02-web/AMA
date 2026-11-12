"""Creierul de brand (docs/10): memoria clientului, în compartimente cu intrări versionate.

Restul aplicației folosește doar ce se exportă aici:

    from app import creier

    intrare, v1 = creier.creeaza_intrare(
        db, tenant_id=t, compartiment=creier.Compartiment.PROFIL_BRAND, cheie="profil",
        continut={...}, sursa=creier.Sursa(creier.SursaTip.OM), utilizator_id=u,
    )
    v2 = creier.propune_schimbare(db, intrare.id, continut={...}, sursa=..., utilizator_id=u)  # versiune nouă
    creier.aproba(db, intrare.id, v2.nr, utilizator_id=client)       # v1 aprobată înainte devine „înlocuită”
    creier.la_data(db, intrare.id, moment)                           # ce era în vigoare atunci
    creier.istoric(db, intrare.id); creier.diferenta_versiuni(db, intrare.id, 1, 2)
"""

from app.creier.compartimente import (
    COMPARTIMENTE,
    CauzaRetragere,
    Compartiment,
    ContinutInvalid,
    InfoCompartiment,
    Nivel,
    Stare,
    SursaTip,
    inregistreaza_schema,
    valideaza_continut,
)
from app.creier.diferenta import Fel, Schimbare, diferenta
from app.creier.modele import IntrareCreier, VersiuneCreier
from app.creier.versiuni import (
    EroareCreier,
    IntrareInexistenta,
    RegulaCreier,
    Sursa,
    TranzitieNepermisa,
    VersiuneInexistenta,
    aproba,
    citeste,
    creeaza_intrare,
    diferenta_versiuni,
    gaseste_intrare,
    intrare,
    istoric,
    la_data,
    lista,
    propune_schimbare,
    retrage,
    trimite_spre_aprobare,
    versiune_aprobata,
    versiuni_de_expirat,
)

__all__ = [
    "COMPARTIMENTE",
    "CauzaRetragere",
    "Compartiment",
    "ContinutInvalid",
    "EroareCreier",
    "Fel",
    "InfoCompartiment",
    "IntrareCreier",
    "IntrareInexistenta",
    "Nivel",
    "RegulaCreier",
    "Schimbare",
    "Stare",
    "Sursa",
    "SursaTip",
    "TranzitieNepermisa",
    "VersiuneCreier",
    "VersiuneInexistenta",
    "aproba",
    "citeste",
    "creeaza_intrare",
    "diferenta",
    "diferenta_versiuni",
    "gaseste_intrare",
    "inregistreaza_schema",
    "intrare",
    "istoric",
    "la_data",
    "lista",
    "propune_schimbare",
    "retrage",
    "trimite_spre_aprobare",
    "valideaza_continut",
    "versiune_aprobata",
    "versiuni_de_expirat",
]
