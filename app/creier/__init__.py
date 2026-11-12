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

Materialele clientului devin pasaje cu vectori și se caută hibrid (F4.3):

    job = creier.trimite_indexarea(tenant_id, sursa_id, cheie=f"indexare:{colectare_id}")   # flux durabil pe
    `io`
    r = creier.cauta(db, tenant_id=t, intrebare="Cât costă livrarea?", limita=5)            # vectori + text +
    trigrame
    r.rezultate[0].text, .url, .pozitie, .scor; r.degradat  # `True` dacă vectorii nu s-au putut folosi
    creier.trimite_reindexarea(tenant_id, cheie="reindexare:model-nou")  # după schimbarea modelului de
    vectori

Pachetul de context al unei sarcini (F4.7, 10.3): reguli, fapte aprobate și valabile, oferte, ghid, pasaje:

    p = creier.context.construieste(db, tenant_id=t, tip_sarcina="postare_facebook", canal="facebook",
                                    intrebare="…", livrabil_id=l)   # se salvează și se leagă de livrabil
    creier.context.ca_text(p)   # text de prompt; pasajele doar prin `gateway.marcheaza_extern`
"""

import uuid

from app.creier import context, fapte, oferte
from app.creier.cautare import CautareRefuzata, Raspuns, Rezultat, cauta
from app.creier.citat import citat_in_text, verifica_propunere
from app.creier.compartimente import (
    COMPARTIMENTE,
    CauzaRetragere,
    Compartiment,
    ContinutInvalid,
    InfoCompartiment,
    Nivel,
    PoartaInchisa,
    Stare,
    SursaTip,
    inregistreaza_cere_om,
    inregistreaza_poarta,
    inregistreaza_randare,
    inregistreaza_schema,
    valideaza_continut,
)
from app.creier.diferenta import Fel, Schimbare, diferenta
from app.creier.indexare import (
    DimensiuneNepotrivita,
    Parametri,
    StareIndexare,
    dimensiune_coloana,
    numara_de_vectorizat,
    pregateste_sursa,
    surse_de_vectorizat,
    vectorizeaza_lot,
)
from app.creier.indexare import stare as stare_indexare
from app.creier.modele import Extragere, IntrareCreier, Pasaj, VersiuneCreier
from app.creier.pachete import Element, PachetContext
from app.creier.versiuni import (
    EroareCreier,
    IntrareInexistenta,
    RegulaCreier,
    RezumatCompartiment,
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
    propuneri_in_asteptare,
    retrage,
    rezumat_pe_compartimente,
    trimite_spre_aprobare,
    versiune_aprobata,
    versiuni_de_expirat,
)


def trimite_indexarea(tenant_id: uuid.UUID, sursa_id: uuid.UUID, *, cheie: str) -> str:
    """Pune în coadă (`io`) tăierea în pasaje și vectorizarea documentelor sursei (idempotent pe `cheie`)."""
    from app.creier import fluxuri

    return fluxuri.trimite(tenant_id, sursa_id, cheie=cheie)


def trimite_extragerea(tenant_id: uuid.UUID, sursa_id: uuid.UUID, *, cheie: str) -> str:
    """Pune în coadă extragerea faptelor dintr-o sursă (propuneri verificate; aprobarea o dă un om)."""
    from app.creier import fluxuri

    return fluxuri.trimite_extragerea(tenant_id, sursa_id, cheie=cheie)


def trimite_reindexarea(tenant_id: uuid.UUID, *, cheie: str) -> list[str]:
    """După schimbarea modelului de vectori: re-vectorizează pasajele cu vectori vechi ale clientului."""
    from app.creier import fluxuri

    return fluxuri.trimite_reindexarea(tenant_id, cheie=cheie)


__all__ = [
    "COMPARTIMENTE",
    "CautareRefuzata",
    "CauzaRetragere",
    "Compartiment",
    "ContinutInvalid",
    "DimensiuneNepotrivita",
    "Element",
    "EroareCreier",
    "Extragere",
    "Fel",
    "InfoCompartiment",
    "IntrareCreier",
    "IntrareInexistenta",
    "Nivel",
    "PachetContext",
    "Parametri",
    "Pasaj",
    "PoartaInchisa",
    "Raspuns",
    "RegulaCreier",
    "Rezultat",
    "RezumatCompartiment",
    "Schimbare",
    "Stare",
    "StareIndexare",
    "Sursa",
    "SursaTip",
    "TranzitieNepermisa",
    "VersiuneCreier",
    "VersiuneInexistenta",
    "aproba",
    "cauta",
    "citat_in_text",
    "citeste",
    "context",
    "creeaza_intrare",
    "diferenta",
    "diferenta_versiuni",
    "dimensiune_coloana",
    "fapte",
    "gaseste_intrare",
    "inregistreaza_cere_om",
    "inregistreaza_poarta",
    "inregistreaza_randare",
    "inregistreaza_schema",
    "intrare",
    "istoric",
    "la_data",
    "lista",
    "numara_de_vectorizat",
    "oferte",
    "pregateste_sursa",
    "propune_schimbare",
    "propuneri_in_asteptare",
    "retrage",
    "rezumat_pe_compartimente",
    "stare_indexare",
    "surse_de_vectorizat",
    "trimite_extragerea",
    "trimite_indexarea",
    "trimite_reindexarea",
    "trimite_spre_aprobare",
    "valideaza_continut",
    "vectorizeaza_lot",
    "verifica_propunere",
    "versiune_aprobata",
    "versiuni_de_expirat",
]
