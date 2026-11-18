"""F16.6 — reclamele pe TikTok. „Gata când”: pe un cont TikTok al agenției, campania construită din planul aprobat
apare oprită la platformă; pornirea și un buget în plafon trec prin gardianul de buget (F13.5) și executorul de
efecte; un buget peste plafonul pe campanie e refuzat și nu ajunge la TikTok; cifrele se citesc în panou. API-ul
TikTok e SIMULAT (D-026)."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable, Iterator

import pytest

from app.connectors import reclame as registru_reclame
from app.connectors.contract import Token
from app.connectors.publicare.baza import DepozitInMemorie
from app.connectors.reclame.tiktok import CANAL_TOKEN, ContTiktok
from app.db import sesiune_agentie
from app.reclame import Campanie, propuneri, rezultate
from tests.integration.utile_productie import fabrica_clienti, om  # noqa: F401
from tests.integration.utile_reclame import ACUM, AZI, construieste, cont_agentie, depozit, executa_efecte  # noqa: F401
from tests.platforme.tiktok_ads import TiktokAdsSimulat

pytestmark = pytest.mark.db
Fabrica = Callable[..., tuple[uuid.UUID, uuid.UUID]]


@pytest.fixture
def tiktok(depozit: DepozitInMemorie) -> Iterator[TiktokAdsSimulat]:
    sim = TiktokAdsSimulat()
    registru_reclame.inregistreaza("tiktok", ContTiktok(depozit=depozit, transport=sim.transport))
    yield sim
    registru_reclame.uita_tot()


def campanie(cid: uuid.UUID) -> Campanie:
    with sesiune_agentie() as db:
        c = db.get(Campanie, cid)
        assert c is not None
        db.expunge(c)
        return c


def test_campania_tiktok_trece_prin_gardian_si_executor(
    tiktok: TiktokAdsSimulat, depozit: DepozitInMemorie, cont_agentie: Fabrica, om: uuid.UUID
) -> None:
    tenant, cont_id = cont_agentie("tiktok", "7000123")
    depozit.pune(tenant, CANAL_TOKEN, Token(acces=tiktok.token_nou("act")))
    scalare, _ = construieste(cont_id, om)
    c = campanie(scalare)
    assert c.stare == "in_pauza" and tiktok.campanii[c.id_extern]["operation_status"] == "DISABLE"  # type: ignore[index]
    assert len(tiktok.campanii) == 2 and tiktok.reclame, "scalare + test, cu reclamele lor"
    with sesiune_agentie() as db:
        p = propuneri.propune(
            db, scalare, "stare", {"stare": "activa"}, motiv="Pornire", sursa="om", utilizator_id=om
        )
        propuneri.aproba(db, p.id, utilizator_id=om)
    executa_efecte()
    with sesiune_agentie() as db:
        prea = propuneri.propune(
            db, scalare, "buget", {"buget_zilnic_bani": 9_000}, motiv="Mai mult", sursa="strateg"
        )
        assert prea.stare == "refuzata" and any("plafonul pe campanie" in m for m in prea.verdict["motive"])
        with pytest.raises(propuneri.PropunereRefuzata):
            propuneri.aproba(db, prea.id)
    executa_efecte()
    assert tiktok.campanii[c.id_extern]["operation_status"] == "ENABLE"  # type: ignore[index]
    assert all(x["budget"] != 90.0 for x in tiktok.campanii.values()), "nimic peste plafon la platformă"
    # cifrele: citite din raportul TikTok, în bani, în totalurile contului
    tiktok.adauga_rand("campanie", str(c.id_extern), AZI.isoformat(), "12.50", 2000, 40, 3, nume=c.nume)
    assert rezultate.citeste_cont(cont_id, ACUM).startswith("citit")
    with sesiune_agentie() as db:
        t = rezultate.totaluri(db, cont_id, AZI, AZI)
        assert t.cheltuiala_bani == 1250 and t.rezultate == 3
