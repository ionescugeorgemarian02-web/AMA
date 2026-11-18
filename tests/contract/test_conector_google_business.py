"""F16.2 — conectorul Google Business Profile trece suita de contract, pe API simulat (# SIMULAT, D-026)."""

import pytest

from app.connectors.contract import Token
from app.connectors.publicare import DepozitInMemorie
from app.connectors.publicare.google_business import ConectorGoogleBusiness
from app.ids import new_id
from app.operare.motor import EroareDefinitiva
from tests.contract.contract_publicare import ContractPublicare, Mediu
from tests.platforme.google_business import CLIENT_ID, CLIENT_SECRET, GoogleBusinessSimulat


def mediu_gbp() -> Mediu:
    pl, d, tenant = GoogleBusinessSimulat(), DepozitInMemorie(), new_id()
    c = ConectorGoogleBusiness(
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET, depozit=d, transport=pl.transport
    )
    t = pl.token_nou("ya29")
    d.pune(tenant, c.canal, Token(t, None, "1//vechi", pl.cont_extern))
    pachet = {"text": "Program prelungit sâmbătă, până la ora 20.", "link": "https://cofetaria.exemplu.test"}
    return Mediu(c, pl, tenant, pachet, token=t, adrese=pl.adrese)


class TestConectorGoogleBusiness(ContractPublicare):
    @pytest.fixture
    def mediu(self) -> Mediu:
        return mediu_gbp()


def test_locatia_vine_din_cont() -> None:
    pl = GoogleBusinessSimulat()
    c = ConectorGoogleBusiness(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, transport=pl.transport)
    assert c.schimba_cod(pl.cod_valid(), "https://ama.exemplu.test/r").cont_extern == pl.cont_extern
    assert "business.manage" in c.url_autorizare("s", "https://ama.exemplu.test/r")


def test_postarea_respinsa_de_google_e_eroare_definitiva() -> None:
    m = mediu_gbp()
    r = m.conector.trimite(m.efect(text="Text interzis de politică."))
    with pytest.raises(EroareDefinitiva):
        m.conector.stare(m.tenant_id, r.id_extern)
