"""F13.6 — Strategul și înregistrările de decizie. „Gata când”: pe date de probă cu rezultate slabe, Strategul
propune oprirea și trei alternative. Platforma și modelul sunt SIMULATE (# SIMULAT)."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.connectors.publicare.baza import DepozitInMemorie
from app.conturi import Rol
from app.db import sesiune_agentie
from app.reclame import Propunere, propuneri, rezultate, strateg
from tests.furnizor_fals import CerereInregistrata
from tests.integration.conftest import Cont
from tests.integration.test_reclame_urgenta import activeaza, stare
from tests.integration.utile_panou import autentifica
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
from tests.onboarding_utile import ModelFals, model_fals, modele, prompt_complet, raspuns_json  # noqa: F401
from tests.platforme.meta_ads import MarketingSimulat

pytestmark = pytest.mark.db


def ipoteze(c: CerereInregistrata) -> str:
    p = prompt_complet(c)
    assert "Decizia regulilor: opreste" in p and "Audit gratuit · scalare" in p
    return raspuns_json(
        ipoteze=[
            {
                "ipoteza": f"Ipoteza {i}: o ofertă mai concretă aduce cereri mai ieftine",
                "unghi": u,
                "dovezi": "225 lei pe rezultat la 300 de clicuri",
                "cost_estimat_bani": 9_000,
            }
            for i, u in enumerate(("garanția rezultatului", "studiu de caz local", "audit în 24 de ore"), 1)
        ]
    )


def test_pe_date_slabe_strategul_propune_oprirea_si_trei_alternative(
    meta: MarketingSimulat,
    depozit: DepozitInMemorie,
    cont_agentie: Callable[..., tuple[uuid.UUID, uuid.UUID]],
    om: uuid.UUID,
    modele: ModelFals,
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
    admin_engine: Engine,
) -> None:
    modele.handlere["Scrie trei ipoteze alternative"] = ipoteze
    tenant, cont_id = cont_agentie()
    autorizeaza(depozit, meta, tenant)
    scalare, _ = construieste(cont_id, om)
    activeaza(scalare, om)
    for i in range(1, 15):  # două săptămâni slabe: clicuri multe, conversie de 0,5%
        meta.zi(AZI - dt.timedelta(days=i), ctr=0.05, conversie=0.005)
    rezultate.citeste_cont(cont_id, ACUM)

    numar = strateg.revizuieste(ACUM)
    assert numar.get("opreste") == 1, numar
    with sesiune_agentie() as db:
        [d] = [x for x in strateg.ale_contului(db, cont_id) if x.campanie_id == scalare]
        assert d.iesire == "opreste" and d.motiv.startswith("2 ferestre la rând")
        assert len(d.alternative) == 3 and {a["buget_zilnic_test_bani"] for a in d.alternative} == {1_280}
        assert d.observat["fereastra"]["clicuri"] > 0 and d.verificare_la == AZI + dt.timedelta(days=6)
        [pid] = d.propuneri
        p = db.get(Propunere, uuid.UUID(pid))
        assert p is not None and p.stare == "propusa" and p.sursa == "strateg", "oprirea așteaptă omul"
        assert p.dupa == {"stare": "pauza"}
        did = d.id
    assert stare(scalare) == "activa", "Strategul nu oprește singur"
    with sesiune_agentie() as db:
        propuneri.aproba(db, uuid.UUID(pid), utilizator_id=om)
    executa_efecte()
    assert stare(scalare) == "in_pauza"

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    h = client.get(f"/reclame/cont/{cont_id}").text
    assert f'data-decizie="{did}" data-iesire="opreste"' in h and "studiu de caz local" in h
    with pytest.raises(DBAPIError), admin_engine.begin() as c:  # aplicația nu poate rescrie o decizie
        c.execute(text("SET ROLE ama_app"))
        c.execute(text("UPDATE reclame_decizii SET iesire = 'continua'"))
