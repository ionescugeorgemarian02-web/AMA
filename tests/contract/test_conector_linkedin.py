"""F9.5 — conectorul LinkedIn (profil și pagină) trece suita de contract, pe Posts API simulat (# SIMULAT)."""

import pytest

from app.connectors.contract import Token
from app.connectors.publicare import DepozitInMemorie
from app.connectors.publicare.linkedin import ConectorLinkedin
from app.ids import new_id
from tests.contract.contract_publicare import ContractPublicare, Mediu
from tests.platforme.linkedin import CLIENT_ID, CLIENT_SECRET, LinkedinSimulat


def mediu_linkedin(pagina: bool) -> Mediu:
    li, d, tenant = LinkedinSimulat(), DepozitInMemorie(), new_id()
    c = ConectorLinkedin(
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET, pagina=pagina, depozit=d, transport=li.transport
    )
    t = li.token_nou("AQV")
    d.pune(tenant, c.canal, Token(t, None, "AQXvechi", li.organizatie if pagina else li.persoana))
    return Mediu(
        c,
        li,
        tenant,
        {"text": "Cafeneaua Zorilor angajează un barista.", "taguri": ["cariera"]},
        token=t,
        adrese=li.adrese,
    )


class TestConectorLinkedinProfil(ContractPublicare):
    @pytest.fixture
    def mediu(self) -> Mediu:
        return mediu_linkedin(False)


class TestConectorLinkedinPagina(ContractPublicare):
    @pytest.fixture
    def mediu(self) -> Mediu:
        return mediu_linkedin(True)


def test_autorul_vine_din_cont() -> None:
    li = LinkedinSimulat()
    for pagina, autor in ((False, li.persoana), (True, li.organizatie)):
        c = ConectorLinkedin(
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET, pagina=pagina, transport=li.transport
        )
        t = c.schimba_cod(li.cod_valid(), "https://ama.exemplu.test/publicare/autorizare")
        assert t.cont_extern == autor
        assert ("w_organization_social" in c.url_autorizare("s", "https://x.test/r")) is pagina
