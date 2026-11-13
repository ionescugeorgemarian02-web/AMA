"""Bancul de evaluare (K4, F5.7): seturile de aur, matricele de confuzie și poarta F5.

    python -m app.validare.banc            # rulează bancul pe baza configurată și afișează scorurile
    python -m app.validare.banc --json     # aceleași scorurile, JSON

Din cod:

    from app.validare import banc
    sc = banc.executie.ruleaza(banc.seturi.incarca())     # dict cu scorurile (nu scrie nimic în bază)
    rulare = banc.depozit.porneste(db, utilizator_id=u); banc.fluxuri.trimite(rulare.id)   # ca job durabil
"""

from app.validare.banc import depozit, executie, scoruri, seturi
from app.validare.banc import fluxuri as fluxuri

__all__ = ["depozit", "executie", "fluxuri", "scoruri", "seturi"]
