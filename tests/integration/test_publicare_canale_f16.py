"""F16.2 — canalele noi (Pinterest, Google Business Profile, Threads). „Gata când”: pe fiecare, o postare
aprobată pleacă prin executorul de efecte, o singură dată, cu linkul în efect; pe contul unui client canalul rămâne
asistat până la aprobarea aplicației (rândul din `aprobari_api`, migrarea 0104). API-urile sunt SIMULATE (D-026)."""

# ruff: noqa: F811
import uuid
from collections.abc import Iterator
from typing import Any

import pytest

from app.connectors import registru
from app.connectors.publicare.google_business import ConectorGoogleBusiness
from app.connectors.publicare.pinterest import ConectorPinterest
from app.connectors.publicare.threads import ConectorThreads
from app.db import sesiune_tenant
from app.operare import efecte
from app.publicare import canale
from tests.integration.publicare_utile import autorizeaza, cere, efect, livrabil_stare, pune_aprobarea
from tests.integration.utile_productie import fabrica_clienti, livrabil_in_publicare, om, tenant  # noqa: F401
from tests.platforme import google_business as gb
from tests.platforme import pinterest as pi
from tests.platforme import threads as th

pytestmark = pytest.mark.db


@pytest.fixture
def platforme() -> Iterator[dict[str, Any]]:
    registru.uita_tot()
    p, g, t = pi.PinterestSimulat(), gb.GoogleBusinessSimulat(), th.ThreadsSimulat()
    for c in (
        ConectorPinterest(client_id=pi.CLIENT_ID, client_secret=pi.CLIENT_SECRET, transport=p.transport),
        ConectorGoogleBusiness(client_id=gb.CLIENT_ID, client_secret=gb.CLIENT_SECRET, transport=g.transport),
        ConectorThreads(app_id=th.APP_ID, app_secret=th.APP_SECRET, transport=t.transport),
    ):
        registru.inregistreaza(c.canal, c)
    yield {"pinterest": p, "google_business": g, "threads": t}
    registru.uita_tot()


CAZURI = [
    ("pinterest", ("pinterest", "publicare"), {"text": "Tort cu vișine.", "titlu": "Tort",
                                               "imagine_url": "https://media.exemplu.test/t.jpg"}),
    ("google_business", ("google", "business"), {"text": "Program prelungit sâmbătă."}),
    ("threads", ("meta", "threads"), {"text": "Ecler cu fistic, azi."}),
]  # fmt: skip


@pytest.mark.parametrize(("canal", "aprobare", "payload"), CAZURI)
def test_postarea_pleaca_prin_executor_iar_clientul_asteapta_aprobarea(
    tenant: uuid.UUID, om: uuid.UUID, platforme: dict[str, Any], canal: str, aprobare: tuple[str, str],
    payload: dict[str, Any],
) -> None:  # fmt: skip
    pl = platforme[canal]
    autorizeaza(tenant, om, canal, pl.cod_valid(), agentie=False)
    with sesiune_tenant(tenant) as db:
        assert canale.mod(db, tenant, canal).mod is canale.Mod.ASISTAT, "în modul de test, clientul e asistat"
    pune_aprobarea(*aprobare, "aprobata")
    try:
        with sesiune_tenant(tenant) as db:
            assert canale.mod(db, tenant, canal).automat
        lid = livrabil_in_publicare(tenant, om, canal=canal)
        eid = cere(tenant, lid, payload)
        assert efecte.incearca_efect(tenant, eid) == "trimis"
        assert efecte.incearca_efect(tenant, eid) != "trimis" or len(pl.postari) == 1
        assert len(pl.postari) == 1, "o singură postare"
        assert efect(tenant, eid).link.startswith("https://")
        assert livrabil_stare(tenant, lid) == "publicat"
    finally:
        pune_aprobarea(*aprobare, "in_test")
