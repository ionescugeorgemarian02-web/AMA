"""Modulul reclame (F13, docs/16): conturile de reclame, rezultatele citite, planificatorul media,
constructorul de campanii, gardianul de buget, oprirea de urgență, Strategul și Consiliul.

Modelul propune, regulile decid, executorul aplică: nicio schimbare de buget nu depinde de judecata unui
model,
iar efectele la platformă pleacă doar prin executorul de efecte (`app.operare.efecte`).
"""

from app.reclame import (
    consiliu,
    constructor,
    gardian,
    plan,
    propuneri,
    raport,
    rezultate,
    strateg,
    teste,
    urgenta,
)
from app.reclame.modele import (
    Anunt,
    Campanie,
    ContReclame,
    DecizieReclame,
    DosarConsiliu,
    PlanMediaRand,
    Propunere,
    RezultatReclame,
)
from app.reclame.rezultate import ETICHETE_PLATFORME, PLATFORME, ContInvalid, Totaluri

__all__ = [
    "ETICHETE_PLATFORME",
    "PLATFORME",
    "Anunt",
    "Campanie",
    "ContInvalid",
    "ContReclame",
    "DecizieReclame",
    "DosarConsiliu",
    "PlanMediaRand",
    "Propunere",
    "RezultatReclame",
    "Totaluri",
    "consiliu",
    "constructor",
    "gardian",
    "plan",
    "propuneri",
    "raport",
    "rezultate",
    "strateg",
    "teste",
    "urgenta",
]
