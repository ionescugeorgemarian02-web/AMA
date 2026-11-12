"""Producția livrabilelor (F2.3+): stările (7.2), limitele anti-buclă (7.3), aprobări și autonomie (7.4).

Restul aplicației folosește doar ce se exportă aici:

    from app import productie

    l = productie.creeaza(db, tenant_id=t, tip="postare", canal="facebook")
    rez = productie.muta(db, l.id, productie.Stare.PLANIFICAT, productie.Stare.BRIEFAT, componenta="D5")
"""

from app.productie import aprobari, autonomie, intrerupator, limite
from app.productie.bugete import Consum, inregistreaza_consum, poate_consuma
from app.productie.limite import Depasire, Limite
from app.productie.modele import Aprobare, Livrabil, NivelAutonomie, SchimbareAutonomie, Tranzitie
from app.productie.reguli_aprobare import (
    MOTIVE_RESPINGERE,
    Decident,
    Hotarare,
    StareAprobare,
    poate_decide,
)
from app.productie.reguli_autonomie import (
    ETICHETE_CLASA,
    ETICHETE_NIVEL,
    Clasa,
    Decizie,
    Nivel,
    cere_aprobare,
)
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
    Temei,
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
    "ETICHETE_CLASA",
    "ETICHETE_NIVEL",
    "EXCEPTII",
    "MOTIVE_RESPINGERE",
    "NORMALE",
    "STARI_FINALE",
    "Aprobare",
    "Clasa",
    "ConflictStare",
    "Consum",
    "Decident",
    "Decizie",
    "Depasire",
    "EroareProductie",
    "Hotarare",
    "LimitaDepasita",
    "Limite",
    "Livrabil",
    "LivrabilInexistent",
    "Nivel",
    "NivelAutonomie",
    "ProductieOprita",
    "Rezultat",
    "SchimbareAutonomie",
    "Stare",
    "StareAprobare",
    "Temei",
    "Tranzitie",
    "TranzitieNepermisa",
    "TranzitieRefuzata",
    "VersiuneNepotrivita",
    "aprobari",
    "autonomie",
    "cere_aprobare",
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
    "poate_decide",
    "reia_de_om",
    "versiune_noua",
]
