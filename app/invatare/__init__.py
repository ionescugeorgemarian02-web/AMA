"""Modulul invatare (F11, docs/11): playbook-ul evolutiv. Reflectorul propune lecții din loturile închise.

from app import invatare

lot = invatare.reflector.reflecteaza(db, tenant_id)     # None dacă lotul nu e încă plin
invatare.reflector.propuneri(db, tenant_id)             # lecțiile propuse, cu dovezi
"""

from app.invatare import alegere, constitutie, curator, experimente, reflector
from app.invatare.modele import Experiment, Lectie, LectieFolosita, LotReflectie

__all__ = [
    "Experiment",
    "Lectie",
    "LectieFolosita",
    "LotReflectie",
    "alegere",
    "constitutie",
    "curator",
    "experimente",
    "reflector",
]
