"""F14.5 — Scorul de lead și riscul de plecare, ca modele, doar la pragul de date. „Gata când”: bat regulile
simple pe date trecute. Datele trecute peste prag sunt SIMULATE; sub prag se citește CRM-ul real."""

# ruff: noqa: F811
import datetime as dt
import random
import uuid

import pytest
from sqlalchemy import Engine, func, select, text

from app.analiza.sanatate import DateRisc
from app.crm import LeadCrm, registru
from app.db import sesiune_agentie
from app.invatare import modele_client as mc
from app.invatare import predictiv
from tests.integration.utile_productie import om  # noqa: F401

pytestmark = pytest.mark.db
T0 = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
SURSE = list(mc.PUNCTE_SURSA)


def leaduri_simulate(n: int, seed: int = 3) -> list[predictiv.Exemplu]:
    """# SIMULAT: câștigul vine din implicarea mare (≥ 5 note), pe care regula o plafonează la 3, nu din sursă."""
    rng = random.Random(seed)  # noqa: S311
    out = []
    for k in range(n):
        note = rng.randrange(0, 8)
        castigat = rng.random() < (0.8 if note >= 5 else 0.15)
        out.append(mc.exemplu_lead(rng.choice(SURSE), "temei", note, castigat, T0 + dt.timedelta(days=k)))
    return out


def plecari_simulate(n: int, seed: int = 4) -> list[predictiv.Exemplu]:
    """# SIMULAT: pleacă mai ales clienții care aproape nu mai decid nimic; regulile de sănătate nu văd asta."""
    rng = random.Random(seed)  # noqa: S311
    out = []
    for k in range(n):
        acum = T0 + dt.timedelta(days=k)
        decizii = rng.randrange(0, 12)
        d = DateRisc(aprobari_intarziate=rng.randrange(0, 3), decizii=decizii, respingeri=rng.randrange(0, 2),
                     ultima_autentificare=acum - dt.timedelta(days=rng.randrange(0, 40)),
                     client_de_la=acum - dt.timedelta(days=200), abonament_stare=rng.choice(["activ", "restant"]))  # fmt: skip
        out.append(mc.exemplu_plecare(d, acum, rng.random() < (0.7 if decizii < 3 else 0.1)))
    return out


def test_sub_prag_pe_crm_real_regula_ramane(om: uuid.UUID) -> None:
    with sesiune_agentie() as db:
        for i, (sursa, final) in enumerate(
            [("recomandare", "castigat"), ("inbox", "pierdut"), ("resursa", None)]
        ):
            lead, _ = registru.primeste(db, email=f"p{i}-{uuid.uuid4().hex[:6]}@exemplu.ro", firma=f"F{i}{uuid.uuid4().hex[:6]}",
                                        sursa=sursa)  # fmt: skip
            if final == "castigat":
                for e in ("calificat", "oferta_trimisa", "castigat"):
                    registru.muta_etapa(db, lead.id, e, utilizator_id=om)
            elif final == "pierdut":
                registru.muta_etapa(db, lead.id, "pierdut", utilizator_id=om, motiv="fără buget")
        inchise = db.execute(
            select(func.count()).select_from(LeadCrm).where(LeadCrm.etapa.in_(("castigat", "pierdut")))
        ).scalar_one()
        r = mc.ruleaza_lead(db)
        assert (r.stare, r.n_exemple, r.tip, r.tenant_id) == (
            "sub_prag",
            inchise,
            "lead",
            None,
        ) and inchise >= 2
        assert mc.scor_lead(db, "recomandare", "x", 1) == (pytest.approx(50 / 70), "reguli")
        p = mc.ruleaza_plecare(db)
        assert (p.stare, p.n_exemple) == ("sub_prag", 0)  # NECONECTAT: fără istoric de fișe de risc


def test_peste_prag_modelele_bat_regulile_simple_pe_date_trecute(admin_engine: Engine) -> None:
    with sesiune_agentie() as db:
        r = mc.ruleaza_lead(db, exemple=leaduri_simulate(600))
        assert r.stare == "valid", r.metrici
        m = r.metrici
        assert m["auc_model"] > m["auc_referinta"] and m["interval"][0] > predictiv.MARJA
        scor, sursa = mc.scor_lead(db, "resursa", "temei", 6)
        assert sursa == "model" and scor > mc.scor_lead(db, "recomandare", "temei", 0)[0]
        p = mc.ruleaza_plecare(db, exemple=plecari_simulate(500))
        assert p.stare == "valid", p.metrici
        assert p.metrici["interval"][0] > predictiv.MARJA and p.referinta == "reguli"
        acum = T0 + dt.timedelta(days=400)
        risc_mic = mc.risc_plecare(db, DateRisc(decizii=10, ultima_autentificare=acum, client_de_la=T0), acum)
        risc_mare = mc.risc_plecare(db, DateRisc(decizii=0, ultima_autentificare=acum, client_de_la=T0), acum)
        assert risc_mic[1] == risc_mare[1] == "model" and risc_mare[0] > risc_mic[0]
    with admin_engine.connect() as c:
        assert c.execute(
            text("SELECT count(*) FROM urme WHERE componenta = 'invatare.predictiv' AND actiune = 'antreneaza_lead'")
        ).scalar_one() >= 1  # fmt: skip
    with sesiune_agentie() as db:  # un model nou care nu bate regula o înlocuiește înapoi pe regulă
        bune = [predictiv.Exemplu(e.trasaturi, e.eticheta, e.moment, float(e.trasaturi["note"] >= 5))
                for e in leaduri_simulate(600)]  # fmt: skip
        assert mc.ruleaza_lead(db, exemple=bune).stare == "nu_bate"
        assert mc.scor_lead(db, "resursa", "temei", 6)[1] == "reguli"
