"""# SIMULAT: campania de probă pe contul agenției, accelerată (F13.10, D-014). Paisprezece zile trec în câteva
secunde: în fiecare zi platforma simulată cheltuie (cu ritm variabil, sub buget), site-ul primește vizite cu acord
și cereri de audit, iar platforma rulează exact ce rulează jobul orar (citire, supraveghere, teste, executor) și,
săptămânal, Strategul. Ceasul e controlat: fiecare pas primește `acum` explicit."""

import datetime as dt
import random
import uuid
from dataclasses import dataclass, field

from app.db import sesiune_agentie
from app.reclame import propuneri, rezultate, strateg, teste, urgenta
from app.site import analiza as analiza_site
from app.site.modele import Lead
from tests.integration.utile_reclame import AZI, construieste, executa_efecte
from tests.platforme.meta_ads import MarketingSimulat

ZILE = 14
PRIMA_ZI = AZI - dt.timedelta(days=ZILE - 1)
PARTE_CU_ACORD = 0.6  # vizitatorii care acceptă analiza
PARTE_LEADURI = (
    0.8  # din rezultatele platformei, câte cereri ajung în site (restul: atribuire după vizualizare)
)


@dataclass
class Jurnal:
    campanii: list[uuid.UUID]
    anomalii: list[str] = field(default_factory=list)
    decizii: list[str] = field(default_factory=list)


def _site(zi: dt.date, clicuri: int, rezultate_: int) -> None:
    for _ in range(int(clicuri * PARTE_CU_ACORD)):
        analiza_site.inregistreaza("/audit", zi=zi)
    la = dt.datetime.combine(zi, dt.time(14), dt.UTC)
    with sesiune_agentie() as db:
        for _ in range(int(rezultate_ * PARTE_LEADURI)):
            db.add(
                Lead(
                    email=f"{uuid.uuid4().hex[:8]}@exemplu.test",
                    firma="Firmă din reclamă",
                    site_url="https://exemplu.test",
                    sursa="audit",
                    stare="confirmat",
                    jeton_hash=uuid.uuid4().hex,
                    consimtamant_la=la,
                    confirmat_la=la,
                    creat_la=la,
                )
            )


def porneste(cont_id: uuid.UUID, om: uuid.UUID) -> list[uuid.UUID]:
    ids = construieste(cont_id, om)
    for cid in ids:
        with sesiune_agentie() as db:
            p = propuneri.propune(
                db,
                cid,
                "stare",
                {"stare": "activa"},
                motiv="Lansarea campaniei de probă",
                sursa="om",
                utilizator_id=om,
            )
            propuneri.aproba(db, p.id, utilizator_id=om)
        executa_efecte()
    return ids


def ruleaza(meta: MarketingSimulat, cont_id: uuid.UUID, om: uuid.UUID, *, samanta: int = 13) -> Jurnal:
    j = Jurnal(porneste(cont_id, om))
    rng = random.Random(samanta)  # noqa: S311
    for k in range(ZILE):
        zi = PRIMA_ZI + dt.timedelta(days=k)
        inainte = meta.manager(zi, zi)
        meta.zi(zi, ritm=rng.uniform(0.85, 1.0), ctr=0.03, conversie=0.12)
        dupa = meta.manager(zi, zi)
        _site(zi, dupa["clicuri"] - inainte["clicuri"], dupa["rezultate"] - inainte["rezultate"])
        acum = dt.datetime.combine(zi, dt.time(23), dt.UTC)
        rezultate.citeste_cont(cont_id, acum)
        j.anomalii += [a.cod for a in urgenta.supravegheaza(acum)]
        teste.evalueaza_toate(acum)
        executa_efecte()
        if k % 7 == 6:  # luni dimineață, după o săptămână întreagă
            j.decizii += list(strateg.revizuieste(acum + dt.timedelta(hours=8)))
            executa_efecte()
    return j
