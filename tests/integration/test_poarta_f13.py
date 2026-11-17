"""Poarta F13: oprirea de urgență este testată pe o campanie reală și nicio schimbare nu a trecut de plafoane.

„Campania reală” e campania de probă de 14 zile a agenției, rulată accelerat pe platforma SIMULATĂ (D-014,
# SIMULAT): construită în pauză din planul aprobat, verificată înainte de lansare, activată de om, citită orar,
supravegheată, testată creativ și revizuită de Strateg. În ziua a 15-a, dimineața, cheltuiala o ia razna: oprirea
de urgență pune totul pe pauză la platformă, oprește reclamele, anunță o singură dată, iar repornirea e manuală.
Pe tot parcursul, orice încercare de a trece de plafoane e refuzată și nu ajunge la platformă."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import select

from app.connectors.publicare.baza import DepozitInMemorie
from app.db import sesiune_agentie
from app.operare import opriri
from app.operare.efecte import EfectSistemRand
from app.operare.notificari import Nivel
from app.reclame import Campanie, Propunere, propuneri, raport, rezultate, urgenta
from tests.integration.lant_reclame import PRIMA_ZI, ruleaza
from tests.integration.test_reclame_campanie_proba import site_curat  # noqa: F401
from tests.integration.utile_productie import AnunturiFalse, anunturi, fabrica_clienti, om  # noqa: F401
from tests.integration.utile_reclame import AZI, autorizeaza, cont_agentie, depozit, executa_efecte, meta  # noqa: F401
from tests.platforme.meta_ads import MarketingSimulat

pytestmark = pytest.mark.db


def test_poarta_f13(
    meta: MarketingSimulat,
    depozit: DepozitInMemorie,
    cont_agentie: Callable[..., tuple[uuid.UUID, uuid.UUID]],
    om: uuid.UUID,
    anunturi: AnunturiFalse,
    site_curat: None,
) -> None:
    tenant, cont_id = cont_agentie()
    autorizeaza(depozit, meta, tenant)
    j = ruleaza(meta, cont_id, om)
    assert j.anomalii == [] and anunturi.trimise == []
    scalare = j.campanii[0]

    # încercări de a trece de plafoane, din toate sursele automate și de la om: toate refuzate
    with sesiune_agentie() as db:
        for sursa, buget in (("strateg", 9_000), ("consiliu", 12_000), ("regula", 8_500), ("om", 9_500)):
            p = propuneri.propune(
                db, scalare, "buget", {"buget_zilnic_bani": buget}, motiv="Mai mult buget", sursa=sursa
            )
            assert p.stare == "refuzata" and p.verdict["cere_client"], sursa

    # ziua 15, ora 6: cheltuiala de dimineață e deja de peste trei ori ritmul planificat
    zi = AZI + dt.timedelta(days=1)
    acum = dt.datetime.combine(zi, dt.time(6), dt.UTC)
    meta.zi(zi, ritm=0.85)
    rezultate.citeste_cont(cont_id, acum)
    assert [a.cod for a in urgenta.supravegheaza(acum)] == ["ritm"]
    executa_efecte()
    assert {c["status"] for c in meta.campanii()} == {"PAUSED"}, "totul pe pauză la platformă"
    cheltuit = meta.manager(zi, zi)["bani"]
    meta.zi(zi)  # restul zilei: nimic nu mai cheltuie
    assert meta.manager(zi, zi)["bani"] == cheltuit
    assert anunturi.nivele() == [Nivel.CRITIC]
    with sesiune_agentie() as db:
        assert opriri.este_oprit(db, opriri.Oprire.RECLAME)
        assert all(
            c.stare == "in_pauza"
            for c in db.execute(select(Campanie).where(Campanie.cont_id == cont_id)).scalars()
        )
        p = propuneri.propune(db, scalare, "stare", {"stare": "activa"}, motiv="Repornire", sursa="strateg")
        assert p.stare == "refuzata", "sub oprire nimic nu repornește"

    # nicio schimbare nu a trecut de plafoane: nici în cifre, nici în istoricul propunerilor
    with sesiune_agentie() as db:
        assert raport.depasiri(db, cont_id, PRIMA_ZI, zi) == []
        refuzate = list(
            db.execute(
                select(Propunere).where(Propunere.cont_id == cont_id, Propunere.stare == "refuzata")
            ).scalars()
        )
        assert len(refuzate) >= 5 and all(p.efect_id is None for p in refuzate), (
            "un refuz nu pleacă la platformă"
        )
        aplicate = list(
            db.execute(
                select(Propunere).where(Propunere.cont_id == cont_id, Propunere.stare == "aplicata")
            ).scalars()
        )
        assert aplicate and all(p.verdict["permis"] for p in aplicate)
        efecte = db.execute(select(EfectSistemRand).where(EfectSistemRand.tip == "reclama")).scalars().all()
        assert {str(e.payload["propunere"]) for e in efecte} <= {str(p.id) for p in aplicate} | {
            str(p.id)
            for p in db.execute(
                select(Propunere).where(Propunere.stare.in_(("aprobata", "esuata")))
            ).scalars()
        }

    # repornirea e manuală: oprirea se ridică de om, campaniile rămân în pauză până le activează el
    with sesiune_agentie() as db:
        opriri.seteaza(db, opriri.Oprire.RECLAME, False, canal="panou", motiv="verificat", utilizator_id=om)
    assert urgenta.supravegheaza(acum + dt.timedelta(hours=1)) == [], "cheltuiala de dinainte nu reoprește"
    executa_efecte()
    assert {c["status"] for c in meta.campanii()} == {"PAUSED"} and len(anunturi.trimise) == 1
