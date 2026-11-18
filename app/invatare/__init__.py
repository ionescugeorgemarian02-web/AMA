"""Modulul invatare (F11, docs/11): playbook-ul evolutiv. Reflectorul propune lecții din loturile închise.

from app import invatare

lot = invatare.reflector.reflecteaza(db, tenant_id)     # None dacă lotul nu e încă plin
invatare.reflector.propuneri(db, tenant_id)             # lecțiile propuse, cu dovezi
invatare.optimizator.optimizeaza(db, "continut.hookuri")  # F14.1: candidat + raport, față de campion
invatare.promovare.porneste(db, optimizare_id)            # F14.2: umbră → canar → producție → promovat
invatare.predictor.ruleaza_client(db, tenant_id, "facebook")  # F14.3: doar peste pragul de date
invatare.teste_ab.declara(db, ipoteza=…, …); invatare.teste_ab.evalueaza(db, test_id)  # F14.4
invatare.modele_client.scor_lead(db, sursa, temei, note)  # F14.5: modelul doar dacă bate regulile
invatare.consolidare.consolideaza(db, tenant_id)  # F14.6: fără dubluri, nefolositele ies din rotație
"""

from app.invatare import (
    alegere,
    consolidare,
    constitutie,
    curator,
    experimente,
    modele_client,
    optimizator,
    predictiv,
    predictor,
    promovare,
    prompturi,
    reflector,
    teste_ab,
)
from app.invatare.modele import (
    Experiment,
    ExperimentFormal,
    Lectie,
    LectieFolosita,
    LotReflectie,
    ModelPredictiv,
    ObservatieFormala,
    ObservatiePromovare,
    Optimizare,
    Promovare,
)

__all__ = [
    "Experiment",
    "ExperimentFormal",
    "Lectie",
    "LectieFolosita",
    "LotReflectie",
    "ModelPredictiv",
    "ObservatieFormala",
    "ObservatiePromovare",
    "Optimizare",
    "Promovare",
    "alegere",
    "consolidare",
    "constitutie",
    "curator",
    "experimente",
    "modele_client",
    "optimizator",
    "predictiv",
    "predictor",
    "promovare",
    "prompturi",
    "reflector",
    "teste_ab",
]
