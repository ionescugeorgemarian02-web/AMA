"""Producția livrabilelor (F2.3+): stările (7.2), limitele anti-buclă (7.3), aprobări și autonomie (7.4).

Restul aplicației folosește doar ce se exportă aici:

    from app import productie

    l = productie.creeaza(db, tenant_id=t, tip="postare", canal="facebook")
    rez = productie.muta(db, l.id, productie.Stare.PLANIFICAT, productie.Stare.BRIEFAT, componenta="D5")
"""

from app.productie.modele import Livrabil, Tranzitie
from app.productie.stari import (
    ETICHETE,
    EXCEPTII,
    NORMALE,
    STARI_FINALE,
    Stare,
    este_permisa,
    motiv_refuz,
)
from app.productie.tranzitii import (
    ConflictStare,
    EroareProductie,
    LivrabilInexistent,
    Rezultat,
    TranzitieNepermisa,
    TranzitieRefuzata,
    VersiuneNepotrivita,
    citeste,
    creeaza,
    istoric,
    muta,
    versiune_noua,
)

__all__ = [
    "ETICHETE",
    "EXCEPTII",
    "NORMALE",
    "STARI_FINALE",
    "ConflictStare",
    "EroareProductie",
    "Livrabil",
    "LivrabilInexistent",
    "Rezultat",
    "Stare",
    "Tranzitie",
    "TranzitieNepermisa",
    "TranzitieRefuzata",
    "VersiuneNepotrivita",
    "citeste",
    "creeaza",
    "este_permisa",
    "istoric",
    "motiv_refuz",
    "muta",
    "versiune_noua",
]
