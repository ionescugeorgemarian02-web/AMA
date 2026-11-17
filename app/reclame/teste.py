"""Testarea creativurilor (F13.9, I4, docs/16 §16.6).

Campania de test (din plan: o singură variabilă, 2–3 variante, buget mic și egal) are un test. Evaluarea
zilnică calculează, pe fiecare variantă, probabilitatea de a fi cea mai bună la rezultate pe afișare
(Beta(1 + rezultate, 1 + afișări − rezultate), Monte Carlo cu sămânță fixă: același rezultat la aceleași
cifre). Câștigătoarea se declară când probabilitatea trece de `PRAG` (90%) și fiecare variantă are datele
minime ale planului (afișări și clicuri). Atunci: pierzătoarele se opresc (propuneri `test`), câștigătoarea
trece în campania de scalare (propunerea `adauga_anunt`), iar cifrele tuturor variantelor rămân în test
(memoria de performanță).
"""

import datetime as dt
import random
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import sesiune_agentie
from app.operare import audit
from app.reclame import plan as plan_media
from app.reclame import propuneri, rezultate
from app.reclame.modele import Anunt, Campanie, ExperimentCreativ, PlanMediaRand

PRAG = 0.9
EXTRAGERI = 20_000


def probabilitati(cifre: list[tuple[int, int]], *, samanta: int = 7) -> list[float]:
    """Nucleu pur: (afișări, rezultate) pe variantă → probabilitatea fiecăreia de a fi cea mai bună."""
    rng = random.Random(samanta)  # noqa: S311  (simulare statistică, nu criptografie)
    castiguri = [0] * len(cifre)
    for _ in range(EXTRAGERI):
        valori = [rng.betavariate(1 + r, 1 + max(0, a - r)) for a, r in cifre]
        castiguri[valori.index(max(valori))] += 1
    return [c / EXTRAGERI for c in castiguri]


def decide(
    cifre: list[tuple[int, int, int]], criterii: plan_media.CriteriiOprire
) -> tuple[int | None, list[float], str]:
    """(afișări, clicuri, rezultate) pe variantă → (câștigătoarea sau None, probabilitățile, motivul)."""
    p = probabilitati([(a, r) for a, _, r in cifre])
    lipsa = [
        i for i, (a, k, _) in enumerate(cifre) if a < criterii.afisari_minime or k < criterii.clicuri_minime
    ]
    if lipsa:
        return None, p, "nu toate variantele au datele minime"
    i = max(range(len(p)), key=lambda k: p[k])
    if p[i] < PRAG:
        return None, p, f"cea mai bună are {p[i]:.0%}, sub pragul de {PRAG:.0%}"
    return i, p, f"probabilitatea de a fi cea mai bună: {p[i]:.0%}"


def asigura(db: Session, c: Campanie) -> ExperimentCreativ:
    t = db.execute(
        select(ExperimentCreativ).where(ExperimentCreativ.campanie_id == c.id)
    ).scalar_one_or_none()
    if t is None:
        t = ExperimentCreativ(tenant_id=c.tenant_id, campanie_id=c.id, variabila=c.variabila or "hook")
        db.add(t)
        db.flush()
    return t


def evalueaza(db: Session, campanie_id: uuid.UUID, acum: dt.datetime) -> ExperimentCreativ | None:
    c = db.get(Campanie, campanie_id)
    if c is None or c.rol != "test" or c.plan_id is None:
        return None
    t = asigura(db, c)
    if t.stare != "in_curs":
        return t
    pr = db.get(PlanMediaRand, c.plan_id)
    if pr is None:
        return t
    criterii = plan_media.plan_din(pr).criterii_oprire
    anunturi = [
        a
        for a in db.execute(select(Anunt).where(Anunt.campanie_id == c.id).order_by(Anunt.nume)).scalars()
        if a.id_extern and a.stare in ("activa", "oprita")
    ]
    if len(anunturi) < 2:
        return t
    de_la = t.inceput_la.date() - dt.timedelta(days=1)
    tot = [
        rezultate.totaluri(db, c.cont_id, de_la, acum.date(), obiect_extern=a.id_extern, nivel="reclama")
        for a in anunturi
    ]
    i, p, motiv = decide([(x.afisari, x.clicuri, x.rezultate) for x in tot], criterii)
    t.variante = [
        {
            "anunt_id": str(a.id),
            "varianta": a.varianta,
            "afisari": x.afisari,
            "clicuri": x.clicuri,
            "rezultate": x.rezultate,
            "probabilitate": round(pi, 4),
        }
        for a, x, pi in zip(anunturi, tot, p, strict=True)
    ]
    t.motiv = motiv
    if i is None:
        return t
    castigator = anunturi[i]
    t.stare, t.castigator_anunt_id, t.incheiat_la = "incheiat", castigator.id, acum
    for a in anunturi:
        if a.id != castigator.id and a.stare == "activa":
            pr_ = propuneri.propune(
                db,
                c.id,
                "stare_anunt",
                {"stare": "pauza"},
                anunt_id=a.id,
                sursa="test",
                motiv=f"Pierde testul ({a.varianta}): {motiv}",
                acum=acum,
            )
            if pr_.stare == "propusa":
                propuneri.aproba(db, pr_.id)
    scalare = db.execute(
        select(Campanie).where(
            Campanie.plan_id == c.plan_id, Campanie.rol == "scalare", Campanie.id_extern.is_not(None)
        )
    ).scalar_one_or_none()
    if scalare is not None:
        nou = Anunt(
            tenant_id=c.tenant_id,
            campanie_id=scalare.id,
            nume=f"{scalare.nume} · castigator-{plan_media.slug(castigator.varianta)}",
            varianta=castigator.varianta,
            titlu=castigator.titlu,
            text=castigator.text,
            link=castigator.link,
            generat_ai=castigator.generat_ai,
            verificare=castigator.verificare,
        )
        db.add(nou)
        db.flush()
        pr_ = propuneri.propune(
            db,
            scalare.id,
            "adauga_anunt",
            {"stare": "activa"},
            anunt_id=nou.id,
            sursa="test",
            motiv=f"Câștigă testul ({castigator.varianta}): {motiv}",
            acum=acum,
        )
        if pr_.stare == "propusa":
            propuneri.aproba(db, pr_.id)
    audit.record(
        db,
        "reclame.test_incheiat",
        obiect_tip="reclame_test",
        obiect_id=t.id,
        tenant_id=t.tenant_id,
        actor_tip="sistem",
        detalii={"castigator": castigator.varianta, "motiv": motiv},
    )
    return t


def evalueaza_toate(acum: dt.datetime | None = None) -> dict[str, int]:
    acum = acum or dt.datetime.now(dt.UTC)
    with sesiune_agentie() as db:
        ids = list(
            db.execute(
                select(Campanie.id).where(Campanie.rol == "test", Campanie.stare == "activa")
            ).scalars()
        )
    numar: dict[str, int] = {}
    for cid in ids:
        with sesiune_agentie() as db:
            t = evalueaza(db, cid, acum)
            if t is not None:
                numar[t.stare] = numar.get(t.stare, 0) + 1
    return numar


def ale_contului(db: Session, cont_id: uuid.UUID) -> list[ExperimentCreativ]:
    q = (
        select(ExperimentCreativ)
        .join(Campanie, Campanie.id == ExperimentCreativ.campanie_id)
        .where(Campanie.cont_id == cont_id)
        .order_by(ExperimentCreativ.inceput_la.desc())
    )
    return list(db.execute(q).scalars())
