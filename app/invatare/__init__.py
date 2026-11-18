"""Modulul invatare (F11, docs/11): playbook-ul evolutiv. Reflectorul propune lecții din loturile închise.

from app import invatare

lot = invatare.reflector.reflecteaza(db, tenant_id)     # None dacă lotul nu e încă plin
invatare.reflector.propuneri(db, tenant_id)             # lecțiile propuse, cu dovezi
invatare.optimizator.optimizeaza(db, "continut.hookuri")  # F14.1: candidat + raport, față de campion
"""

from app.invatare import alegere, constitutie, curator, experimente, optimizator, prompturi, reflector
from app.invatare.modele import Experiment, Lectie, LectieFolosita, LotReflectie, Optimizare

__all__ = [
    "Experiment",
    "Lectie",
    "LectieFolosita",
    "LotReflectie",
    "Optimizare",
    "alegere",
    "constitutie",
    "curator",
    "experimente",
    "optimizator",
    "prompturi",
    "reflector",
]
