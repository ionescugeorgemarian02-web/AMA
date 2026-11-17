"""F13.9 — testarea creativurilor. „Gata când”: un test cu trei variante și buget mic declară un câștigător după
regulile din 16.6. Platforma e SIMULATĂ (# SIMULAT); cheltuiala pe zile vine din simulator."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable

import pytest

from app.connectors.publicare.baza import DepozitInMemorie
from app.db import sesiune_agentie
from app.reclame import Campanie, constructor, rezultate, teste
from tests.integration.test_reclame_urgenta import activeaza
from tests.integration.utile_productie import fabrica_clienti, om  # noqa: F401
from tests.integration.utile_reclame import (  # noqa: F401
    ACUM,
    AZI,
    autorizeaza,
    construieste,
    cont_agentie,
    depozit,
    executa_efecte,
    meta,
)
from tests.platforme.meta_ads import MarketingSimulat

pytestmark = pytest.mark.db


def test_trei_variante_buget_mic_declara_un_castigator(
    meta: MarketingSimulat,
    depozit: DepozitInMemorie,
    cont_agentie: Callable[..., tuple[uuid.UUID, uuid.UUID]],
    om: uuid.UUID,
) -> None:
    tenant, cont_id = cont_agentie()
    autorizeaza(depozit, meta, tenant)
    scalare, test = construieste(cont_id, om)
    activeaza(scalare, om)
    activeaza(test, om)
    with sesiune_agentie() as db:
        c = db.get(Campanie, test)
        assert c is not None and c.buget_zilnic_bani == 1_600, "buget mic: 20% din zi"
        ads = {a.varianta: a.id_extern for a in constructor.anunturi(db, test)}
        teste.asigura(db, c).inceput_la = ACUM - dt.timedelta(days=10)
    meta.obiecte[ads["Trei greșeli de pe site"]]["conversie"] = 0.25  # varianta care chiar convinge
    meta.zi(AZI - dt.timedelta(days=9), ctr=0.02)  # o zi: încă prea puține date pentru o decizie
    rezultate.citeste_cont(cont_id, ACUM)
    with sesiune_agentie() as db:
        t = teste.evalueaza(db, test, ACUM)
        assert t is not None and t.stare == "in_curs" and "datele minime" in t.motiv
    for zi in range(2, 10):
        meta.zi(AZI - dt.timedelta(days=10 - zi), cpm_bani=500, ctr=0.02)
    rezultate.citeste_cont(cont_id, ACUM)
    with sesiune_agentie() as db:
        cheltuieli = {
            v: rezultate.totaluri(
                db, cont_id, AZI - dt.timedelta(days=30), AZI, obiect_extern=e, nivel="reclama"
            ).cheltuiala_bani
            for v, e in ads.items()
        }
        assert len(set(cheltuieli.values())) == 1, "buget egal între variante"
        assert teste.evalueaza_toate(ACUM) == {"incheiat": 1}
        [t] = teste.ale_contului(db, cont_id)
        castigatoare = next(v for v in t.variante if v["anunt_id"] == str(t.castigator_anunt_id))
        assert castigatoare["varianta"] == "Trei greșeli de pe site" and castigatoare["probabilitate"] > 0.9
        assert all(v["afisari"] >= 1_000 for v in t.variante), "fiecare variantă are datele minime"
    executa_efecte()
    pierzatoare = [e for v, e in ads.items() if v != "Trei greșeli de pe site"]
    assert {meta.obiecte[e]["status"] for e in pierzatoare} == {"PAUSED"}
    assert meta.obiecte[ads["Trei greșeli de pe site"]]["status"] == "ACTIVE"
    with sesiune_agentie() as db:
        s = db.get(Campanie, scalare)
        assert s is not None
        noi = [a for a in constructor.anunturi(db, scalare) if "castigator" in a.nume]
    assert len(noi) == 1 and noi[0].stare == "activa" and noi[0].id_extern in meta.obiecte
    assert meta.obiecte[noi[0].id_extern]["campaign_id"] == s.id_extern, "câștigătoarea trece în scalare"
