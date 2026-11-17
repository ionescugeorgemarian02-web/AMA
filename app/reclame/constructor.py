"""Constructorul de campanii (F13.4, I2, docs/16 §16.3 pasul 5): din planul aprobat, campaniile în pauză.

Fiecare campanie din plan devine un rând `reclame_campanii` cu reclamele ei (scalare: un creativ; test:
unul pe
variantă) și o propunere `creeaza`, aprobată de sistem (planul a fost aprobat de om) și aplicată prin
executor.
Platforma primește campania cu starea PAUSED; activarea e o propunere separată (16.1, punctul 4).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.reclame import plan as plan_media
from app.reclame import propuneri
from app.reclame.modele import Anunt, Campanie, PlanMediaRand


@dataclass(frozen=True)
class Creativ:
    titlu: str
    text: str
    generat_ai: bool = False


class ConstructieRefuzata(ValueError):
    pass


def construieste(
    db: Session, plan_id: uuid.UUID, creative: dict[str, Creativ], *, utilizator_id: uuid.UUID | None = None
) -> list[Campanie]:
    """`creative`: textul fiecărei variante (cheia = varianta din plan; „scalare” pentru campania de
    scalare)."""
    r = db.get(PlanMediaRand, plan_id)
    if r is None or r.stare != "aprobat":
        raise ConstructieRefuzata("campaniile se construiesc doar dintr-un plan aprobat")
    if db.execute(select(Campanie.id).where(Campanie.plan_id == plan_id)).first() is not None:
        raise ConstructieRefuzata("planul a fost deja construit")
    p = plan_media.plan_din(r)
    facute: list[Campanie] = []
    for cp in p.campanii:
        c = Campanie(
            tenant_id=r.tenant_id,
            cont_id=r.cont_id,
            plan_id=r.id,
            nume=cp.nume,
            rol=cp.rol,
            variabila=cp.variabila,
            buget_zilnic_bani=cp.buget_zilnic_bani,
        )
        db.add(c)
        db.flush()
        variante = cp.variante if cp.rol == "test" else ["scalare"]
        for v in variante:
            cr = creative.get(v)
            if cr is None:
                raise ConstructieRefuzata(f"lipsește creativul pentru „{v}”")
            db.add(
                Anunt(
                    tenant_id=r.tenant_id,
                    campanie_id=c.id,
                    nume=f"{cp.nume} · {plan_media.slug(v)}",
                    varianta=v,
                    titlu=cr.titlu,
                    text=cr.text,
                    generat_ai=cr.generat_ai,
                    link=plan_media.link_cu_utm(p, v),
                )
            )
        db.flush()
        pr = propuneri.propune(
            db,
            c.id,
            "creeaza",
            {"stare": "pauza", "obiectiv": p.obiectiv, "buget_zilnic_bani": c.buget_zilnic_bani},
            motiv=f"Construită în pauză din planul aprobat ({p.masurare.utm_campaign})",
            sursa="constructor",
            utilizator_id=utilizator_id,
        )
        if pr.stare == "propusa":
            propuneri.aproba(db, pr.id, utilizator_id=utilizator_id)
        facute.append(c)
    return facute


def campanii(db: Session, cont_id: uuid.UUID) -> list[Campanie]:
    q = select(Campanie).where(Campanie.cont_id == cont_id).order_by(Campanie.creat_la, Campanie.nume)
    return list(db.execute(q).scalars())


def anunturi(db: Session, campanie_id: uuid.UUID) -> list[Anunt]:
    return list(
        db.execute(select(Anunt).where(Anunt.campanie_id == campanie_id).order_by(Anunt.nume)).scalars()
    )
