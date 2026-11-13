"""Exemplele propuse pentru setul de aur (F5.7, alimentate de F5.8 și F5.10).

Fluxul (docs/11 constituția: învățarea nu are drept de scriere asupra seturilor de aur):
1. O contestație (F5.10) sau o etichetă umană „greșit” (F5.8) PROPUNE un exemplu (`propune`): stare `propus`,
pe client.
2. Un om al agenției îl PROMOVEAZĂ (`promoveaza`, cu profilul de context, eticheta și, dacă e nevoie, textul
anonimizat) sau îl
   respinge. Un exemplu promovat intră în rularea bancului (`promovate_ca_exemple`).
3. Pentru a-l face permanent în depozit, un om îl exportă (`exporta_jsonl`) și îl pune într-un commit în
`evaluare/aur/`.
   Codul NU scrie în depozit.
"""

import datetime as dt
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ids import new_id
from app.operare import audit
from app.validare import continut as continut_mod
from app.validare.banc.seturi import VALIDATORI, Exemplu
from app.validare.modele import ExempluPropus, VerdictSalvat


class ExempluInvalid(ValueError):
    """Propunerea sau decizia nu respectă regulile."""


def propune(
    db: Session,
    verdict: VerdictSalvat,
    *,
    sursa: str,
    asteptat: str,
    severitate: str | None,
    motiv: str,
    utilizator_id: uuid.UUID | None,
    tip: str,
    canal: str,
) -> tuple[ExempluPropus, bool]:
    """Propune exemplul din textul verdictului. Idempotent pe (verdict, sursă). Întoarce (exemplul, creat)."""
    if asteptat not in ("trece", "esec") or (asteptat == "esec") != (severitate in ("majora", "critica")):
        raise ExempluInvalid("eticheta cere `trece`, sau `esec` cu severitate majora / critica")
    existent = db.execute(
        select(ExempluPropus).where(ExempluPropus.verdict_id == verdict.id, ExempluPropus.sursa == sursa)
    ).scalar_one_or_none()
    if existent is not None:
        return existent, False
    c = continut_mod.citeste(db, verdict.livrabil_id, verdict.versiune)
    e = ExempluPropus(
        id=new_id(),
        tenant_id=verdict.tenant_id,
        validator=verdict.validator,
        sursa=sursa,
        verdict_id=verdict.id,
        livrabil_id=verdict.livrabil_id,
        versiune=verdict.versiune,
        tip=tip,
        canal=canal,
        text=c.text[:20000],
        campuri=dict(c.campuri),
        active=list(c.active),
        asteptat=asteptat,
        severitate=severitate,
        motiv=motiv.strip()[:500],
        creat_de=utilizator_id,
    )
    db.add(e)
    db.flush()
    return e, True


def listeaza(db: Session, *, stare: str | None = "propus", limita: int = 200) -> list[ExempluPropus]:
    q = select(ExempluPropus)
    if stare:
        q = q.where(ExempluPropus.stare == stare)
    return list(db.execute(q.order_by(ExempluPropus.creat_la, ExempluPropus.id).limit(limita)).scalars())


def _decide(
    db: Session,
    exemplu_id: uuid.UUID,
    *,
    stare: str,
    utilizator_id: uuid.UUID,
    motiv: str,
    acum: dt.datetime | None = None,
) -> ExempluPropus:
    e = db.execute(
        select(ExempluPropus).where(ExempluPropus.id == exemplu_id).with_for_update()
    ).scalar_one_or_none()
    if e is None:
        raise LookupError(str(exemplu_id))
    if e.stare != "propus":
        raise ExempluInvalid(f"exemplul e deja „{e.stare}”")
    e.stare, e.decis_de, e.motiv_decizie = stare, utilizator_id, motiv.strip()[:500]
    e.decis_la = acum or dt.datetime.now(dt.UTC)
    db.flush()
    audit.record(
        db,
        f"exemplu_aur.{stare}",
        obiect_tip="exemplu_propus",
        obiect_id=e.id,
        utilizator_id=utilizator_id,
        tenant_id=e.tenant_id,
        detalii={"validator": e.validator, "sursa": e.sursa, "context": e.context_profil},
    )
    return e


def promoveaza(
    db: Session,
    exemplu_id: uuid.UUID,
    *,
    utilizator_id: uuid.UUID,
    context_profil: str = "gol",
    text: str | None = None,
    asteptat: str | None = None,
    severitate: str | None = None,
    motiv: str = "",
    acum: dt.datetime | None = None,
) -> ExempluPropus:
    """Decizia unui om: exemplul intră în setul de aur. Omul poate corecta eticheta și anonimiza textul
    (exemplul vine
    din materialul unui client). Profilul de context trebuie să existe în `contexte.toml`."""
    from app.validare.banc.seturi import citeste_contexte

    if context_profil not in citeste_contexte()[1]:
        raise ExempluInvalid(f"profil de context necunoscut: {context_profil}")
    e = db.get(ExempluPropus, exemplu_id)
    if e is None:
        raise LookupError(str(exemplu_id))
    if e.validator not in VALIDATORI:
        raise ExempluInvalid(f"{e.validator} nu are set de aur în banc")
    if text is not None:
        if not text.strip():
            raise ExempluInvalid("textul promovat nu poate fi gol")
        e.text = text.strip()[:20000]
    if asteptat is not None:
        if asteptat not in ("trece", "esec") or (asteptat == "esec") != (severitate in ("majora", "critica")):
            raise ExempluInvalid("eticheta cere `trece`, sau `esec` cu severitate majora / critica")
        e.asteptat, e.severitate = asteptat, severitate
    e.context_profil = context_profil
    return _decide(db, exemplu_id, stare="promovat", utilizator_id=utilizator_id, motiv=motiv, acum=acum)


def respinge(
    db: Session,
    exemplu_id: uuid.UUID,
    *,
    utilizator_id: uuid.UUID,
    motiv: str,
    acum: dt.datetime | None = None,
) -> ExempluPropus:
    return _decide(db, exemplu_id, stare="respins", utilizator_id=utilizator_id, motiv=motiv, acum=acum)


def ca_exemplu(e: ExempluPropus) -> Exemplu:
    return Exemplu(
        id=f"p-{str(e.id)[:8]}",
        set=f"promovat:{e.validator}",
        ctx=e.context_profil,
        tip=e.tip,
        canal=e.canal,
        text=e.text,
        campuri=dict(e.campuri),
        active=tuple(e.active),
        asteptat=e.asteptat,
        severitate=e.severitate,
        motiv=e.motiv or e.motiv_decizie or "promovat de un om",
        validator=e.validator,
    )


def promovate_ca_exemple(db: Session) -> tuple[Exemplu, ...]:
    """Exemplele promovate de oameni, gata pentru banc (citite în scop de agenție)."""
    return tuple(ca_exemplu(e) for e in listeaza(db, stare="promovat", limita=1000))


def exporta_jsonl(db: Session) -> str:
    """Exemplele promovate ca rânduri JSONL, pentru ca un om să le pună într-un commit în
    `evaluare/aur/<G>.jsonl`."""
    linii: list[str] = []
    for e in listeaza(db, stare="promovat", limita=1000):
        d: dict[str, Any] = {
            "id": f"p-{str(e.id)[:8]}",
            "ctx": e.context_profil,
            "tip": e.tip,
            "canal": e.canal,
            "text": e.text,
            "campuri": e.campuri,
            "active": e.active,
            "asteptat": e.asteptat,
            "severitate": e.severitate,
            "motiv": e.motiv or e.motiv_decizie,
            "validator": e.validator,
        }
        linii.append(json.dumps(d, ensure_ascii=False))
    return "\n".join(linii)
