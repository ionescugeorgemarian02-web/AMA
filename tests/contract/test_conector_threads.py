"""F16.2 — conectorul Threads trece suita de contract, pe Threads API simulat (# SIMULAT, D-026)."""

import pytest

from app.connectors.contract import Token
from app.connectors.publicare import DepozitInMemorie
from app.connectors.publicare.threads import ConectorThreads
from app.ids import new_id
from tests.contract.contract_publicare import ContractPublicare, Mediu
from tests.platforme.threads import APP_ID, APP_SECRET, ThreadsSimulat


def mediu_threads() -> Mediu:
    pl, d, tenant = ThreadsSimulat(), DepozitInMemorie(), new_id()
    c = ConectorThreads(app_id=APP_ID, app_secret=APP_SECRET, depozit=d, transport=pl.transport)
    t = pl.token_nou("THL")
    d.pune(tenant, c.canal, Token(t, None, "", pl.utilizator))
    pachet = {"text": "Azi avem ecler cu fistic, proaspăt.", "taguri": ["desert"]}
    return Mediu(c, pl, tenant, pachet, token=t, adrese=pl.adrese)


class TestConectorThreads(ContractPublicare):
    @pytest.fixture
    def mediu(self) -> Mediu:
        return mediu_threads()


def test_utilizatorul_vine_din_cont_si_textul_e_taiat_la_500() -> None:
    pl = ThreadsSimulat()
    c = ConectorThreads(app_id=APP_ID, app_secret=APP_SECRET, transport=pl.transport)
    assert c.schimba_cod(pl.cod_valid(), "https://ama.exemplu.test/r").cont_extern == pl.utilizator
    assert len(c.text({"text": "y" * 800})) == 500


def test_limita_de_publicare_scade_cu_fiecare_postare() -> None:
    m = mediu_threads()
    m.conector.trimite(m.efect())
    lim = m.conector.limite(m.tenant_id)
    assert (lim.ramase, lim.total) == (249, 250)
