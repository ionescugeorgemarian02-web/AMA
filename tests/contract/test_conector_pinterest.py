"""F16.2 — conectorul Pinterest trece suita de contract, pe API v5 simulat (# SIMULAT, D-026)."""

import pytest

from app.connectors.contract import Token
from app.connectors.publicare import DepozitInMemorie
from app.connectors.publicare.pinterest import ConectorPinterest
from app.ids import new_id
from app.operare.motor import EroareDefinitiva
from tests.contract.contract_publicare import ContractPublicare, Mediu
from tests.platforme.pinterest import CLIENT_ID, CLIENT_SECRET, PinterestSimulat

PACHET = {"text": "Tort de ciocolată cu vișine, la comandă.", "taguri": ["tort"], "titlu": "Tort cu vișine",
          "imagine_url": "https://media.exemplu.test/tort.jpg", "link": "https://cofetaria.exemplu.test"}  # fmt: skip


def mediu_pinterest() -> Mediu:
    pl, d, tenant = PinterestSimulat(), DepozitInMemorie(), new_id()
    c = ConectorPinterest(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, depozit=d, transport=pl.transport)
    t = pl.token_nou("pina")
    d.pune(tenant, c.canal, Token(t, None, "pinr_vechi", pl.panou))
    return Mediu(c, pl, tenant, dict(PACHET), token=t, adrese=pl.adrese)


class TestConectorPinterest(ContractPublicare):
    @pytest.fixture
    def mediu(self) -> Mediu:
        return mediu_pinterest()


def test_pinul_fara_imagine_e_refuzat_definitiv() -> None:
    m = mediu_pinterest()
    with pytest.raises(EroareDefinitiva):
        m.conector.trimite(m.efect(imagine_url=""))
    assert m.platforma.postari_publicate() == []


def test_panoul_vine_din_cont_si_descrierea_e_taiata() -> None:
    pl = PinterestSimulat()
    c = ConectorPinterest(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, transport=pl.transport)
    assert c.schimba_cod(pl.cod_valid(), "https://ama.exemplu.test/r").cont_extern == pl.panou
    assert len(c.descriere({"text": "x" * 900})) == 500
