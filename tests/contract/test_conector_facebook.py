"""F9.2 — conectorul Facebook Pages trece suita de contract, pe Graph API simulat (# SIMULAT, contract HTTP
local)."""

import pytest

from app.connectors.contract import Token
from app.connectors.publicare import DepozitInMemorie
from app.connectors.publicare.facebook import ConectorFacebook, procent_din_antete
from app.ids import new_id
from tests.contract.contract_publicare import ContractPublicare, Mediu
from tests.platforme.meta import APP_ID, APP_SECRET, GraphSimulat


class TestConectorFacebook(ContractPublicare):
    @pytest.fixture
    def mediu(self) -> Mediu:
        g, d, tenant = GraphSimulat(), DepozitInMemorie(), new_id()
        t = g.token_nou("EAAP")
        d.pune(tenant, "facebook", Token(t, None, "", g.pagina))
        c = ConectorFacebook(app_id=APP_ID, app_secret=APP_SECRET, depozit=d, transport=g.transport)
        return Mediu(
            c,
            g,
            tenant,
            {"text": "Cafeneaua Zorilor: espresso la 7 dimineața.", "taguri": ["cafea"]},
            token=t,
            adrese=g.adrese,
        )


def test_procentul_din_antetele_meta() -> None:
    antete = {"x-business-use-case-usage": '{"1001": [{"type": "pages", "call_count": 42, "total_time": 7}]}'}
    assert procent_din_antete(antete) == (42.0, "antetul x-business-use-case-usage")
    assert procent_din_antete({}) == (None, "")
