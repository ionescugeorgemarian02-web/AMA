"""Joburile programate ale gateway-ului: curățarea zilnică a contoarelor vechi și a conținutului expirat
(20.4)."""

import datetime as dt
import uuid
from typing import Any

from app.db import sesiune_agentie
from app.gateway import bugete, evaluare, jurnal, limitator, registru
from app.gateway.amanare import reprogrameaza
from app.gateway.erori import Amanat
from app.operare import motor
from app.operare.motor import Coada, Prioritate

NUME_CURATARE = "gateway.curatare"


@motor.pas(nume="gateway.pas_curatare")
def _curata() -> str:
    contoare = limitator.curata()
    continut = jurnal.curata_continut()
    consum = bugete.curata_vechi()
    return f"contoare={contoare} continut={continut} consum={consum}"


@motor.flux(NUME_CURATARE)
def curatare(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    """O dată pe zi (03:17, ora României): contoarele și blocajele de peste 3 zile, conținutul apelurilor
    peste 30 de zile."""
    return _curata()


NUME_EVALUARE = "gateway.evaluare"
NUME_EVALUARE_LUNARA = "gateway.evaluare_lunara"


@motor.pas(nume="gateway.pas_evaluare")
def _evalueaza(model_cod: str, rulare_id: str) -> str:
    r = evaluare.ruleaza(model_cod, rulare_id=uuid.UUID(rulare_id) if rulare_id else None)
    if r.stare == "amanata" and r.amanata_pana_la is not None:
        return f"amanata:{r.id}:{r.amanata_pana_la.isoformat()}"
    return f"terminata:{r.id}"


@motor.flux(NUME_EVALUARE)
def evalueaza(model_cod: str, rulare_id: str) -> str:
    """Testul comparativ pe un model (P3). La amânare, își reprogramează continuarea (aceeași rulare)."""
    rezultat = _evalueaza(model_cod, rulare_id)
    if rezultat.startswith("amanata:"):
        _, rid, moment = rezultat.split(":", 2)
        reprogrameaza(
            Amanat(dt.datetime.fromisoformat(moment), "cota testului comparativ"), evalueaza, model_cod, rid,
            cheie=f"evaluare:{rid}", coada=coada_pentru(model_cod), prioritate=Prioritate.P3,
        )  # fmt: skip
    return rezultat


def coada_pentru(model_cod: str) -> Coada:
    """Modelul local se apelează doar din joburi `greu` (F3.5); restul, pe coada de învățare."""
    with sesiune_agentie() as db:
        local = any(c.cod == model_cod and c.fara_cheie for c in registru.candidati(db))
    return Coada.GREU if local else Coada.INVATARE


@motor.pas(nume="gateway.pas_evaluare_lunara")
def _porneste_evaluari(luna: str) -> str:
    with sesiune_agentie() as db:
        coduri = [
            c.cod for c in registru.candidati(db)
            if c.stare_furnizor == "activ" and c.model_activ and "embeddings" not in c.capabilitati
        ]  # fmt: skip
    for cod in coduri:
        motor.trimite(
            evalueaza,
            cod,
            "",
            coada=coada_pentru(cod),
            prioritate=Prioritate.P3,
            cheie=f"evaluare:{luna}:{cod}",
        )
    return f"modele={len(coduri)}"


@motor.flux(NUME_EVALUARE_LUNARA)
def evaluare_lunara(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    """Lunar (8.10): testul comparativ pe fiecare model activ (la un model nou: din panou sau comandă)."""
    return _porneste_evaluari(moment.strftime("%Y-%m"))


def declara_programari() -> None:
    motor.programeaza_recurent(NUME_EVALUARE_LUNARA, "40 4 2 * *", evaluare_lunara, coada=Coada.INVATARE)
    motor.programeaza_recurent(NUME_CURATARE, "17 3 * * *", curatare)


declara_programari()
