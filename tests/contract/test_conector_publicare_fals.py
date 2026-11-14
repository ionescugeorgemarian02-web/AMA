"""F9.1 — conectorul fals (# SIMULAT, în memorie) trece toate testele de contract ale conectorilor de
publicare."""

import pytest

from app.connectors.publicare import DepozitInMemorie
from app.connectors.publicare.fals import ConectorFalsPublicare, PlatformaFalsa
from app.ids import new_id
from tests.contract.contract_publicare import ContractPublicare, Mediu


class TestConectorFals(ContractPublicare):
    @pytest.fixture
    def mediu(self) -> Mediu:
        p, d, tenant = PlatformaFalsa(), DepozitInMemorie(), new_id()
        t = p.emite_token()
        d.pune(tenant, "fals_api", t)
        return Mediu(
            ConectorFalsPublicare(p, d),
            p,
            tenant,
            {"text": "Cafeneaua Zorilor: cafea de specialitate."},
            token=t.acces,
        )
