"""Producția livrabilelor (F2.3+): stările (7.2), limitele anti-buclă (7.3), aprobări și autonomie (7.4).

Restul aplicației folosește doar ce se exportă aici:

    from app import productie

    l = productie.creeaza(db, tenant_id=t, tip="postare", canal="facebook")
    rez = productie.muta(db, l.id, productie.Stare.PLANIFICAT, productie.Stare.BRIEFAT, componenta="D5")
"""

from app.productie import intrerupator, limite
from app.productie.bugete import Consum, inregistreaza_consum, poate_consuma
from app.productie.limite import Depasire, Limite
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
    LimitaDepasita,
    LivrabilInexistent,
    ProductieOprita,
    Rezultat,
    TranzitieNepermisa,
    TranzitieRefuzata,
    VersiuneNepotrivita,
    citeste,
    creeaza,
    istoric,
    muta,
    reia_de_om,
    versiune_noua,
)

__all__ = [
    "ETICHETE",
    "EXCEPTII",
    "NORMALE",
    "STARI_FINALE",
    "ConflictStare",
    "Consum",
    "Depasire",
    "EroareProductie",
    "LimitaDepasita",
    "Limite",
    "Livrabil",
    "LivrabilInexistent",
    "ProductieOprita",
    "Rezultat",
    "Stare",
    "Tranzitie",
    "TranzitieNepermisa",
    "TranzitieRefuzata",
    "VersiuneNepotrivita",
    "citeste",
    "creeaza",
    "este_permisa",
    "inregistreaza_consum",
    "intrerupator",
    "istoric",
    "limite",
    "motiv_refuz",
    "muta",
    "poate_consuma",
    "reia_de_om",
    "versiune_noua",
]
