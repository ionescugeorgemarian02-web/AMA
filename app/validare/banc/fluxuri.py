"""Bancul ca job durabil (ADR-03): butonul din panou și comanda din terminal pornesc același flux. Fluxul
primește doar
identificatorul rulării; seturile se citesc din depozit și din exemplele promovate, scorurile se salvează în
`banc_rulari`."""

import uuid

from app.db import sesiune_agentie
from app.logging import get_logger
from app.operare import motor
from app.operare.motor import Coada, Prioritate
from app.validare import exemple
from app.validare.banc import depozit, executie, seturi

log = get_logger("app.validare.banc")
NUME = "validare.banc"


def ruleaza_si_salveaza(rulare_id: uuid.UUID) -> str:
    """Rulează bancul pentru o rulare deja deschisă și salvează rezultatul. Întoarce starea finală."""
    try:
        with sesiune_agentie() as db:
            promovate = exemple.promovate_ca_exemple(db)
        sc = executie.ruleaza(seturi.incarca(promovate=promovate))
        with sesiune_agentie() as db:
            depozit.termina(db, rulare_id, sc)
        return "terminat"
    except Exception as exc:
        log.error("rularea bancului a eșuat", extra={"tip_eroare": type(exc).__name__})
        with sesiune_agentie() as db:
            depozit.esueaza(db, rulare_id, f"{type(exc).__name__}: {exc}")
        return "esuat"


@motor.pas(nume="validare.banc_pas", reincercari=0)
def _pas(rulare_id: str) -> str:
    return ruleaza_si_salveaza(uuid.UUID(rulare_id))


@motor.flux(NUME, timp_maxim_sec=900)
def ruleaza_banc(rulare_id: str) -> str:
    return _pas(rulare_id)


def trimite(rulare_id: uuid.UUID) -> str:
    """Pune bancul în coadă (idempotent pe rulare). Întoarce identificatorul jobului."""
    return motor.trimite(
        ruleaza_banc,
        str(rulare_id),
        coada=Coada.INVATARE,
        prioritate=Prioritate.P3,
        cheie=f"banc:{rulare_id}",
    )
