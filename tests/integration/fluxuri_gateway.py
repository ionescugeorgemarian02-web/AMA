"""# SIMULAT: fluxul de probă al amânării (F3.3). Un flux durabil care apelează un model fixat; la `Amanat` își
reprogramează munca prin motor, pentru momentul resetării cotei, în loc să doarmă sau să eșueze."""

import os
import uuid

from app import gateway
from app.db import sesiune_agentie
from app.gateway import apel, registru
from app.gateway.iesire import Iesire
from app.gateway.tipuri import Mesaj
from app.operare import motor


class Raspuns(Iesire):
    eticheta: str


MESAJE = (Mesaj("user", "Spune ceva."),)


@motor.pas(nume="proba_gw.apel")
def _apel(model_id: str, incercare: int) -> str:
    with sesiune_agentie() as db:
        candidat = registru.candidat(db, uuid.UUID(model_id))
    assert candidat is not None
    try:
        apel.apeleaza_pe_model(candidat, os.environ.get("AMA_CHEIE_PROBA"), MESAJE, Raspuns)
    except gateway.Amanat as amanat:
        gateway.reprogrameaza(
            amanat, flux_proba, model_id, incercare + 1, cheie=f"proba_gw:{model_id}:{incercare}"
        )
        return "amanat"
    return "ok"


@motor.flux("proba_gw.flux")
def flux_proba(model_id: str, incercare: int) -> str:
    return _apel(model_id, incercare)
