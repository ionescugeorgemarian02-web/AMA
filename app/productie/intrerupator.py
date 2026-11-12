"""Întrerupătorul global (7.3): rata de eșec peste prag într-o fereastră → producția NOUĂ se oprește.

- Eșec = intrare în `coada_de_erori`; succes = intrare în `validat` (producția a ajuns la capăt).
  Un livrabil care ajunge la `validat` și apoi în coada de erori la publicare numără o dată ca succes și
  o dată ca eșec: acceptat, spus în `docs/specs/F2.4.md`.
- Pragul (30%), fereastra (60 min) și volumul minim (10 rezultate) sunt configurabile; sub volumul minim nu se
  judecă (1 eșec din 2 nu oprește nimic).
- Declanșarea pune `Oprire.PRODUCTIE` (canal „sistem”), scrie auditul și anunță CRITIC (push + Telegram).
- REPORNIREA o face doar un om (`opriri.seteaza(..., False, utilizator_id=…)`: butonul din panou sau
  Telegram), cu audit. Nimic din acest modul nu repornește. După repornire, rezultatele de dinainte nu
  mai contează (fereastra începe de la repornire), altfel întrerupătorul s-ar declanșa din nou imediat.
- Evaluarea citește rezultatele tuturor clienților, deci rulează într-o sesiune de agenție (jobul programat
  din `fluxuri`); nicio decizie a unui client nu atinge datele altuia.
"""

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.operare import opriri
from app.operare.notificari import Nivel
from app.operare.opriri import Oprire
from app.productie import limite
from app.productie.anunturi import anunta
from app.productie.modele import Tranzitie
from app.productie.stari import Stare


@dataclass(frozen=True)
class Evaluare:
    succese: int
    esecuri: int
    rata: float | None
    de_la: dt.datetime
    declansat_acum: bool  # această evaluare a oprit producția
    oprit: bool  # producția nouă este oprită (acum sau dinainte)


def _numara(db: Session, de_la: dt.datetime, pana_la: dt.datetime) -> tuple[int, int]:
    q = (
        select(Tranzitie.in_stare, func.count())
        .where(
            Tranzitie.rezultat == "aplicata",
            Tranzitie.in_stare.in_((Stare.VALIDAT.value, Stare.COADA_DE_ERORI.value)),
            Tranzitie.creat_la >= de_la,
            Tranzitie.creat_la <= pana_la,
        )
        .group_by(Tranzitie.in_stare)
    )
    nr = dict(db.execute(q).all())
    return int(nr.get(Stare.VALIDAT.value, 0)), int(nr.get(Stare.COADA_DE_ERORI.value, 0))


def evalueaza(db: Session, *, acum: dt.datetime | None = None) -> Evaluare:
    """Evaluează fereastra și, dacă rata a depășit pragul, oprește producția nouă. Sesiune de agenție."""
    s = get_settings()
    acum = acum or dt.datetime.now(dt.UTC)
    de_la = acum - dt.timedelta(minutes=s.intrerupator_fereastra_min)
    rand = opriri.citeste(db, Oprire.PRODUCTIE)
    if rand is not None and rand.activ:
        succese, esecuri = _numara(db, de_la, acum)
        return Evaluare(succese, esecuri, limite.rata_esec(succese, esecuri), de_la, False, True)
    if rand is not None:  # repornit de om: fereastra începe de la repornire
        de_la = max(de_la, rand.schimbat_la)
    succese, esecuri = _numara(db, de_la, acum)
    rata = limite.rata_esec(succese, esecuri)
    declansat = limite.intrerupator_declansat(
        succese, esecuri, s.intrerupator_prag_esec, s.intrerupator_volum_min
    )
    if declansat:
        total = succese + esecuri
        motiv = (
            f"Întrerupător global: {esecuri} eșecuri din {total} rezultate "
            f"({(rata or 0) * 100:.0f}%) în ultimele {s.intrerupator_fereastra_min} min, peste pragul de "
            f"{s.intrerupator_prag_esec * 100:.0f}%"
        )
        opriri.seteaza(db, Oprire.PRODUCTIE, True, canal="sistem", motiv=motiv)
        anunta(
            db,
            Nivel.CRITIC,
            "Producția nouă s-a oprit",
            f"Rata de eșec a depășit pragul: {esecuri} din {total}. Repornirea o face un om, din panou.",
            url="/",
        )
    return Evaluare(succese, esecuri, rata, de_la, declansat, declansat)


def blocaj(db: Session, tenant_id: uuid.UUID) -> str | None:
    """Motivul pentru care producția nouă NU are voie acum (pentru fluxuri și ecrane), sau `None`."""
    if opriri.este_oprit(db, Oprire.PRODUCTIE, tenant_id=tenant_id):
        return "producția nouă este oprită (global sau pentru acest client)"
    return None
