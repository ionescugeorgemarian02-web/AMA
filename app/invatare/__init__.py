"""Modulul invatare (F11, docs/11): playbook-ul evolutiv. Reflectorul propune lecții din loturile închise.

from app import invatare

lot = invatare.reflector.reflecteaza(db, tenant_id)     # None dacă lotul nu e încă plin
invatare.reflector.propuneri(db, tenant_id)             # lecțiile propuse, cu dovezi
invatare.optimizator.optimizeaza(db, "continut.hookuri")  # F14.1: candidat + raport, față de campion
invatare.promovare.porneste(db, optimizare_id)            # F14.2: umbră → canar → producție → promovat
invatare.predictor.ruleaza_client(db, tenant_id, "facebook")  # F14.3: doar peste pragul de date
"""

from app.invatare import (
    alegere,
    constitutie,
    curator,
    experimente,
    optimizator,
    promovare,
    prompturi,
    reflector,
)
from app.invatare.modele import (
    Experiment,
    Lectie,
    LectieFolosita,
    LotReflectie,
    ObservatiePromovare,
    Optimizare,
    Promovare,
)

__all__ = [
    "Experiment",
    "Lectie",
    "LectieFolosita",
    "LotReflectie",
    "ModelPredictiv",
    "ObservatiePromovare",
    "Optimizare",
    "Promovare",
    "alegere",
    "constitutie",
    "curator",
    "experimente",
    "optimizator",
    "predictiv",
    "predictor",
    "promovare",
    "prompturi",
    "reflector",
]
