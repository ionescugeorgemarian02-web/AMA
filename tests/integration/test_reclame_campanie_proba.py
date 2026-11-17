"""F13.10 — campania de probă pe contul agenției, cu buget mic, către pagina de audit. „Gata când”: trec două
săptămâni fără depășire de plafon, cu raport dublu: platformă și site. Simulare accelerată (D-014, # SIMULAT):
platforma e simulată, site-ul și toată platforma AMA sunt reale."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.connectors.publicare.baza import DepozitInMemorie
from app.conturi import Rol
from app.db import sesiune_agentie
from app.reclame import raport
from tests.integration.conftest import Cont
from tests.integration.lant_reclame import PRIMA_ZI, ZILE, ruleaza
from tests.integration.utile_panou import autentifica
from tests.integration.utile_productie import fabrica_clienti, om  # noqa: F401
from tests.integration.utile_reclame import AZI, autorizeaza, cont_agentie, depozit, meta  # noqa: F401
from tests.platforme.meta_ads import MarketingSimulat

pytestmark = pytest.mark.db


@pytest.fixture
def site_curat(admin_engine: Engine) -> Iterator[None]:
    def sterge() -> None:
        with admin_engine.begin() as c:  # tabelele site-ului sunt ale agenției, comune pe sesiunea de teste
            c.execute(text("DELETE FROM site_vizite"))
            c.execute(text("DELETE FROM audituri"))
            c.execute(text("DELETE FROM leaduri"))

    sterge()
    yield
    sterge()


def test_doua_saptamani_fara_depasire_de_plafon_cu_raport_dublu(
    meta: MarketingSimulat,
    depozit: DepozitInMemorie,
    cont_agentie: Callable[..., tuple[uuid.UUID, uuid.UUID]],
    om: uuid.UUID,
    site_curat: None,
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
) -> None:
    tenant, cont_id = cont_agentie()  # buget mic: plafon 100 lei/zi, 3.000 lei/lună, 80 lei pe campanie
    autorizeaza(depozit, meta, tenant)
    j = ruleaza(meta, cont_id, om)
    assert j.anomalii == [], "două săptămâni fără nicio oprire de urgență"
    assert len(j.decizii) >= 2, "Strategul a revizuit în fiecare săptămână"
    with sesiune_agentie() as db:
        assert raport.depasiri(db, cont_id, PRIMA_ZI, AZI) == []
        r = raport.raport_dublu(db, cont_id, PRIMA_ZI, AZI)
    m = meta.manager(PRIMA_ZI, AZI)
    assert len(r.zile) == ZILE and r.platforma.cheltuiala_bani == m["bani"] > 0
    assert all(0 < z.platforma.cheltuiala_bani <= 10_000 for z in r.zile)
    assert 0 < r.vizite_audit < r.platforma.clicuri and 0 < r.cereri_audit < r.platforma.rezultate
    assert len(r.explicatii) == 2, "diferențele platformă–site se explică"

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    h = client.get(f"/reclame/cont/{cont_id}/raport?zile={ZILE}").text
    assert 'data-plafoane="respectate"' in h and "Vizite audit (site)" in h and "Cereri de audit (site)" in h
    assert f"<td>{r.vizite_audit}</td>" in h and "acceptat analiza" in h
