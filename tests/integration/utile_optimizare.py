"""Ajutoare pentru testele optimizatorului (F14): un prompt de probă cu nume unic, setul de aur real al
hook-urilor și un model SIMULAT, determinist, a cărui calitate depinde de instrucțiunile din mesajul de sistem."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app import gateway
from app.continut.scriere import PropunereHookuri
from app.db import sesiune_agentie
from app.invatare import optimizator
from app.invatare.optimizator import Exemplu, Varianta

INSTRUCTIUNE_BUNA = "Folosește în fiecare hook cuvintele-cheie concrete din brief."
INSTRUCTIUNE_SLABA = "Scrie hook-uri cât mai scurte."
SISTEM_CAMPION = "Ești generatorul de hook-uri. Scrii în română, cu diacritice, fără promisiuni false."
SABLON = "Livrabil: {{tip}} pe {{canal}}.\nBrief:\n{{brief}}\n{{exemple}}"


def prompt_de_proba(sistem: str = SISTEM_CAMPION, *, profil: str = "creatie") -> str:
    """Un prompt nou (nume unic), activ la versiunea 1, cu schema hook-urilor."""
    nume = f"proba.optim_{uuid.uuid4().hex[:10]}"
    with sesiune_agentie() as db:
        gateway.prompturi.creeaza(
            db, nume, profil=profil, sablon=SABLON, sistem=sistem, schema=PropunereHookuri
        )
        gateway.prompturi.activeaza(db, nume, 1)
    return nume


def set_aur() -> list[Exemplu]:
    return optimizator.incarca_set("continut.hookuri")


def model_simulat(db: Session, referinta: str, ex: Exemplu) -> dict[str, Any] | None:
    """# SIMULAT: în locul gateway-ului. Cu instrucțiunea bună, hook-urile folosesc cuvintele-cheie din criterii."""
    p = gateway.prompturi.rezolva(db, referinta)
    assert p is not None
    return model_simulat_text(INSTRUCTIUNE_BUNA in p.sistem, ex.criterii.get("cuvinte_obligatorii", []))


def model_simulat_text(buna: bool, cheie: list[str], *, partial: bool = False) -> dict[str, Any]:
    """Hook-urile modelului simulat: cu instrucțiunea bună folosesc cuvintele-cheie (cu `partial`, doar primul)."""
    baza = "Află ce pregătim săptămâna aceasta în cartier"
    if buna:
        folosite = cheie[:1] if partial else cheie
        texte = [f"{baza}: {' și '.join(folosite)}.", f"Știai că {cheie[0]} contează?", "De ce acum?"]
    else:
        texte = [f"{baza}.", "Știai că poți încerca ceva nou?", "De ce să mai aștepți?"]
    tipare = ["rezultat", "intrebare", "contraintuitiv"]
    return {"hookuri": [{"text": t, "tipar": tp} for t, tp in zip(texte, tipare, strict=True)]}


def propunator_simulat(
    db: Session, campion: gateway.prompturi.Reperat, picate: list[dict[str, Any]]
) -> list[Varianta]:
    """# SIMULAT: propunătorul reflexiv; o variantă slabă și una bună, ca alegerea pe antrenare să conteze."""
    assert picate, "propunătorul primește exemplele ratate"
    p = optimizator.PropunereReflectie(incredere=0.7, instructiuni=[
        {"instructiune": INSTRUCTIUNE_SLABA, "motiv": "hook-urile lungi se citesc mai greu"},
        {"instructiune": INSTRUCTIUNE_BUNA, "motiv": "exemplele ratate nu foloseau cuvintele-cheie"},
    ])  # fmt: skip
    return optimizator.din_reflectie(campion, p)


def propunator_inutil(
    db: Session, campion: gateway.prompturi.Reperat, picate: list[dict[str, Any]]
) -> list[Varianta]:
    """# SIMULAT: o variantă care nu schimbă nimic din ce contează."""
    return [Varianta(campion.sistem + "\n" + INSTRUCTIUNE_SLABA, campion.sablon, "slabă", "probă")]
