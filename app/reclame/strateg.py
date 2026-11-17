"""Strategul de reclame și înregistrările de decizie (F13.6, docs/07 §7.7, docs/16 §16.9).

Revizuirea săptămânală citește, pe fiecare campanie construită dintr-un plan, fereastra ultimelor 7 zile și
pe cea
de dinainte, și alege una din ieșiri după criteriile planului (reguli, nu model):
- **așteaptă**: sub datele minime (afișări, clicuri și cheltuială de două ori ținta) nu se decide nimic;
- **continuă**: costul pe rezultat sub țintă;
- **ajustează**: peste țintă, dar sub pragul de pierdere (cere creativuri noi; banii nu se mută singuri);
- **pivotează**: peste pragul de pierdere într-o singură fereastră;
- **oprește**: peste prag în `ferestre_slabe` (implicit 2) ferestre la rând, cu date suficiente.
La pivot și la oprire, modelul (gateway, T3) scrie trei ipoteze alternative, de testat pe 20% din buget;
oprirea
devine o propunere de pauză (`strateg`) care așteaptă aprobarea omului. Fiecare decizie e o înregistrare
neschimbabilă: ce s-a văzut, ce s-a decis, ce se așteaptă și când se verifică.
"""

import datetime as dt
import json
import uuid
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import gateway
from app.db import sesiune_agentie
from app.logging import get_logger
from app.operare import audit
from app.operare.motor import Prioritate
from app.reclame import plan as plan_media
from app.reclame import prompturi, propuneri, rezultate
from app.reclame.modele import Anunt, Campanie, DecizieReclame, PlanMediaRand
from app.reclame.rezultate import Totaluri

log = get_logger("app.reclame.strateg")
REFERINTA_PROMPT = "reclame.strateg@1"
FEREASTRA_ZILE = 7
PARTE_PIVOT = 0.2


class Ipoteza(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ipoteza: str = Field(min_length=10, max_length=400)
    unghi: str = Field(min_length=3, max_length=120)
    dovezi: str = Field(min_length=3, max_length=300)
    cost_estimat_bani: int = Field(ge=0)


class PropunereIpoteze(gateway.Iesire):
    ipoteze: list[Ipoteza] = Field(min_length=3, max_length=3)


@dataclass(frozen=True)
class Verdict:
    iesire: str
    motiv: str


def slaba(t: Totaluri, c: plan_media.CriteriiOprire) -> bool | None:
    """`None` = date insuficiente; altfel dacă fereastra e sub pragul minim (CPR peste multiplu × țintă)."""
    suficient = t.afisari >= c.afisari_minime and t.clicuri >= c.clicuri_minime
    suficient = suficient or t.cheltuiala_bani >= 2 * c.cost_tinta_bani
    if not suficient:
        return None
    return t.cheltuiala_bani > c.multiplu_pierdere * c.cost_tinta_bani * max(t.rezultate, 0) or (
        t.rezultate == 0 and t.cheltuiala_bani >= 2 * c.cost_tinta_bani
    )


def judeca(ferestre: list[Totaluri], c: plan_media.CriteriiOprire) -> Verdict:
    """Nucleu pur. `ferestre`: cea curentă prima, apoi cele dinainte."""
    t = ferestre[0]
    s = slaba(t, c)
    cpr = t.cost_pe_rezultat_bani
    if s is None:
        return Verdict(
            "asteapta", "date insuficiente pentru o decizie (afișări, clicuri sau cheltuială sub minim)"
        )
    if s:
        la_rand = 1
        for f in ferestre[1:]:
            if slaba(f, c):
                la_rand += 1
            else:
                break
        text = "fără rezultate" if cpr is None else f"cost pe rezultat {cpr / 100:.2f}"
        if la_rand >= c.ferestre_slabe:
            return Verdict("opreste", f"{la_rand} ferestre la rând sub pragul minim ({text})")
        return Verdict("pivoteaza", f"o fereastră sub pragul minim ({text}); unghiul se schimbă")
    if cpr is not None and cpr > c.cost_tinta_bani:
        return Verdict("ajusteaza", f"cost pe rezultat {cpr / 100:.2f}, peste țintă: creativuri noi")
    return Verdict("continua", "cost pe rezultat sub țintă")


def _cifre(t: Totaluri) -> dict[str, int | None]:
    return {
        "cheltuiala_bani": t.cheltuiala_bani,
        "afisari": t.afisari,
        "clicuri": t.clicuri,
        "rezultate": t.rezultate,
        "cost_pe_rezultat_bani": t.cost_pe_rezultat_bani,
    }


def _ipoteze(
    db: Session, c: Campanie, p: plan_media.PlanMedia, v: Verdict, t: Totaluri
) -> tuple[list[dict[str, object]], str | None]:
    testate = sorted(
        {a.varianta for a in db.execute(select(Anunt).where(Anunt.campanie_id == c.id)).scalars()}
    )
    prompturi.asigura()
    try:
        r = gateway.apeleaza(
            db,
            prompt=REFERINTA_PROMPT,
            schema=PropunereIpoteze,
            tenant_id=c.tenant_id,
            componenta="reclame.strateg",
            variabile={
                "iesire": v.iesire,
                "motiv": v.motiv,
                "campanie": c.nume,
                "testate": ", ".join(testate),
                "cifre": json.dumps(_cifre(t)),
                "pagina": p.pagina_destinatie,
            },
            prioritate=Prioritate.P2,
            max_tokeni=1500,
        )
    except gateway.EroareGateway as exc:  # decizia rămâne (e a regulilor); ipotezele vin la rularea următoare
        log.info("ipotezele Strategului amânate", extra={"tip_eroare": type(exc).__name__})
        return [], None
    if not isinstance(r.iesire, PropunereIpoteze):
        return [], None
    buget_test = int(c.buget_zilnic_bani * PARTE_PIVOT)
    return [i.model_dump() | {"buget_zilnic_test_bani": buget_test} for i in r.iesire.ipoteze], r.model


def revizuieste_campania(db: Session, campanie_id: uuid.UUID, acum: dt.datetime) -> DecizieReclame | None:
    c = db.get(Campanie, campanie_id)
    if c is None or c.plan_id is None or c.id_extern is None:
        return None
    pr = db.get(PlanMediaRand, c.plan_id)
    if pr is None:
        return None
    p = plan_media.plan_din(pr)
    pana_la = acum.date() - dt.timedelta(days=1)
    ferestre: list[Totaluri] = []
    for k in range(p.criterii_oprire.ferestre_slabe + 1):
        sf = pana_la - dt.timedelta(days=FEREASTRA_ZILE * k)
        ferestre.append(
            rezultate.totaluri(
                db, c.cont_id, sf - dt.timedelta(days=FEREASTRA_ZILE - 1), sf, obiect_extern=c.id_extern
            )
        )
    v = judeca(ferestre, p.criterii_oprire)
    alternative: list[dict[str, object]] = []
    model = None
    if v.iesire in ("pivoteaza", "opreste"):
        alternative, model = _ipoteze(db, c, p, v, ferestre[0])
    ids: list[str] = []
    if v.iesire == "opreste" and c.stare == "activa":
        prop = propuneri.propune(
            db, c.id, "stare", {"stare": "pauza"}, motiv=f"Strategul: {v.motiv}", sursa="strateg", acum=acum
        )
        ids.append(str(prop.id))
    asteptat = {
        "continua": "costul pe rezultat rămâne sub țintă",
        "ajusteaza": "creativele noi aduc costul sub țintă în fereastra următoare",
        "pivoteaza": "un unghi nou, testat pe 20% din buget, coboară costul sub prag",
        "opreste": "una dintre cele trei ipoteze, testată pe 20% din buget, trece pragul minim",
        "asteapta": "datele ajung la minim",
    }[v.iesire]
    d = DecizieReclame(
        tenant_id=c.tenant_id,
        cont_id=c.cont_id,
        campanie_id=c.id,
        sursa="strateg",
        de_la=pana_la - dt.timedelta(days=FEREASTRA_ZILE - 1),
        pana_la=pana_la,
        observat={
            "fereastra": _cifre(ferestre[0]),
            "anterioare": [_cifre(f) for f in ferestre[1:]],
            "tinta_bani": p.criterii_oprire.cost_tinta_bani,
        },
        iesire=v.iesire,
        motiv=v.motiv,
        alternative=alternative,
        asteptat=asteptat,
        verificare_la=pana_la + dt.timedelta(days=FEREASTRA_ZILE),
        propuneri=ids,
        model=model,
    )
    db.add(d)
    db.flush()
    audit.record(
        db,
        "reclame.decizie",
        obiect_tip="reclame_decizie",
        obiect_id=d.id,
        tenant_id=c.tenant_id,
        actor_tip="sistem",
        detalii={"iesire": v.iesire, "sursa": "strateg"},
    )
    return d


def revizuieste(acum: dt.datetime | None = None) -> dict[str, int]:
    """Revizuirea săptămânală a tuturor campaniilor construite (active sau în pauză, cu id la platformă)."""
    acum = acum or dt.datetime.now(dt.UTC)
    with sesiune_agentie() as db:
        ids = list(
            db.execute(select(Campanie.id).where(Campanie.stare.in_(("activa", "in_pauza")))).scalars()
        )
    numar: dict[str, int] = {}
    for cid in ids:
        with sesiune_agentie() as db:
            d = revizuieste_campania(db, cid, acum)
            if d is not None:
                numar[d.iesire] = numar.get(d.iesire, 0) + 1
    return numar


def ale_contului(db: Session, cont_id: uuid.UUID, *, limita: int = 30) -> list[DecizieReclame]:
    q = select(DecizieReclame).where(DecizieReclame.cont_id == cont_id)
    return list(db.execute(q.order_by(DecizieReclame.creat_la.desc()).limit(limita)).scalars())
