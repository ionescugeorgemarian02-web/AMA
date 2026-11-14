"""Bara de progres a onboardingului (docs/19 §19.3): pașii, fiecare cu „gata” calculat din starea reală.

Pașii care țin de faze viitoare (conectarea conturilor: F9) se arată, dar nu se socotesc. Un pas nou se adaugă
prin `inregistreaza_pas` (de exemplu plata, F7.6, și materialele, F7.5), din modulul lui."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import creier, productie
from app.creier import Compartiment
from app.onboarding import completare, sesiuni, strategie


@dataclass(frozen=True)
class Pas:
    ordine: int
    nume: str
    gata: bool
    url: str = ""
    viitor: bool = False  # pasul vine într-o fază ulterioară: nu intră în procent


Verificare = Callable[[Session, uuid.UUID], Pas]
_PASI: dict[str, Verificare] = {}


def inregistreaza_pas(cod: str, f: Verificare) -> None:
    _PASI[cod] = f


def _aprobat(db: Session, tenant_id: uuid.UUID, comp: Compartiment, cheie: str) -> bool:
    i = creier.gaseste_intrare(db, tenant_id=tenant_id, compartiment=comp, cheie=cheie)
    return i is not None and creier.versiune_aprobata(db, i.id) is not None


def _interviu(db: Session, t: uuid.UUID) -> Pas:
    s = sesiuni.sesiune_deschisa(db, t)
    trimis = creier.gaseste_intrare(
        db, tenant_id=t, compartiment=Compartiment.BRIEF, cheie=completare.CHEIE_BRIEF
    )
    gata = trimis is not None or (s is not None and sesiuni.progres(db, s.id).terminat)
    return Pas(2, "Răspunde la interviu", gata, "/portal/onboarding")


def _creier(db: Session, t: uuid.UUID) -> Pas:
    gata = _aprobat(db, t, Compartiment.BRIEF, completare.CHEIE_BRIEF)
    return Pas(6, "Corectează și aprobă profilul", gata, "/portal/creier")


def _strategie(db: Session, t: uuid.UUID) -> Pas:
    gata = _aprobat(db, t, Compartiment.STRATEGIE, strategie.CHEIE_STRATEGIE)
    return Pas(7, "Aprobă planul pe 90 de zile", gata, "/portal/creier")


def _primul_lot(db: Session, t: uuid.UUID) -> Pas:
    gata = bool(productie.aprobari.listeaza(db, doar_in_asteptare=False, limita=1))
    return Pas(8, "Primul lot de conținut spre aprobare", gata, "/portal/aprobari")


inregistreaza_pas("cont", lambda db, t: Pas(1, "Activează contul", True))
inregistreaza_pas("interviu", _interviu)
inregistreaza_pas("conturi", lambda db, t: Pas(4, "Conectează conturile sociale", False, viitor=True))
inregistreaza_pas("creier", _creier)
inregistreaza_pas("strategie", _strategie)
inregistreaza_pas("lot", _primul_lot)


def pasi(db: Session, tenant_id: uuid.UUID) -> list[Pas]:
    return sorted((f(db, tenant_id) for f in _PASI.values()), key=lambda p: p.ordine)


def procent(lista: list[Pas]) -> int:
    reale = [p for p in lista if not p.viitor]
    return round(100 * sum(p.gata for p in reale) / len(reale)) if reale else 0
