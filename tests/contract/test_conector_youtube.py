"""F9.4 — conectorul YouTube trece suita de contract, pe YouTube Data API simulat (# SIMULAT, contract HTTP
local); cota în unități se numără cu costurile configurate, pe ziua Pacific (ceas controlat)."""

import datetime as dt

import pytest

from app.connectors.contract import StarePostare, Token
from app.connectors.publicare import DepozitInMemorie
from app.connectors.publicare.youtube import ConectorYoutube, costuri, resetare, zi_pacific
from app.ids import new_id
from app.operare.motor import EroareTemporara
from tests.contract.contract_publicare import ContractPublicare, Mediu
from tests.platforme.google import CLIENT_ID, CLIENT_SECRET, YoutubeSimulat

ACUM = dt.datetime.now(dt.UTC).replace(microsecond=0)  # ceas fix pe durata testului
PACHET = {
    "text": "Cafeneaua Zorilor: cum se face un flat white.",
    "titlu": "Flat white în 30 de secunde",
    "fisier": "clienti/cz/clip.mp4",
    "eticheta_ai": True,
}


class ContorInMemorie:
    def __init__(self) -> None:
        self.zile: dict[tuple[str, dt.date], int] = {}

    def consumat(self, platforma: str, zi: dt.date) -> int:
        return self.zile.get((platforma, zi), 0)

    def adauga(self, platforma: str, zi: dt.date, unitati: int) -> None:
        self.zile[(platforma, zi)] = self.consumat(platforma, zi) + unitati


def conector(y: YoutubeSimulat, cota: int = 10_000) -> tuple[ConectorYoutube, ContorInMemorie]:
    contor = ContorInMemorie()
    c = ConectorYoutube(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        costuri_unitati=costuri("videos.insert=1600,videos.list=1"),
        cota_zi=cota,
        depozit=DepozitInMemorie(),
        contor=contor,
        transport=y.transport,
        ceas=lambda: ACUM,
        citeste_fisier=lambda rel: b"\x00\x00\x00\x18ftypmp42" + rel.encode(),
    )
    return c, contor


class TestConectorYoutube(ContractPublicare):
    @pytest.fixture
    def mediu(self) -> Mediu:
        y = YoutubeSimulat()
        c, _ = conector(y)
        tenant, t = new_id(), y.token_nou("ya29")
        c.depozit.pune(tenant, "youtube", Token(t, ACUM + dt.timedelta(hours=1), "", "UCzorilor"))  # type: ignore[attr-defined]
        return Mediu(
            c, y, tenant, dict(PACHET), stare_asteptata=StarePostare.PRIVATA, token=t, adrese=y.adrese
        )


def test_cota_in_unitati_si_campul_sintetic() -> None:
    y = YoutubeSimulat()
    c, contor = conector(y, cota=2000)
    tenant, t = new_id(), y.token_nou("ya29")
    c.depozit.pune(tenant, "youtube", Token(t, None, "", "UCzorilor"))  # type: ignore[attr-defined]
    m = Mediu(c, y, tenant, {**PACHET, "vizibilitate": "public"})
    c.trimite(m.efect())
    assert y.postari[0]["sintetic"] is True, "eticheta AI → containsSyntheticMedia"
    assert y.postari[0]["vizibilitate"] == "private", "proiect neauditat: platforma ține clipul privat"
    lim = c.limite(tenant)
    assert (lim.ramase, lim.total) == (400, 2000) and lim.resetare_la == resetare(ACUM)
    assert contor.consumat("youtube", zi_pacific(ACUM)) == 1600
    with pytest.raises(EroareTemporara, match="cota YouTube"):
        c.trimite(m.efect(text="Al doilea clip."))
    assert len(y.postari) == 1


def test_ziua_pacific() -> None:
    assert zi_pacific(dt.datetime(2026, 11, 14, 7, 59, tzinfo=dt.UTC)) == dt.date(2026, 11, 13)
    assert zi_pacific(dt.datetime(2026, 11, 14, 8, 1, tzinfo=dt.UTC)) == dt.date(2026, 11, 14)
