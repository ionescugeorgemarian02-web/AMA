"""F9.3 — conectorul Instagram trece suita de contract, pe Graph API simulat (# SIMULAT, contract HTTP
local)."""

from collections.abc import Iterator

import pytest

from app.connectors.contract import Token
from app.connectors.publicare import DepozitInMemorie
from app.connectors.publicare.instagram import ConectorInstagram
from app.ids import new_id
from app.operare.motor import EroareTemporara
from tests.contract.contract_publicare import ContractPublicare, Mediu
from tests.platforme.meta import APP_ID, APP_SECRET, GraphSimulat

PACHET = {
    "text": "Cafeneaua Zorilor: croissant cu unt.",
    "fisier": "clienti/cz/croissant.jpg",
    "tip_media": "imagine",
}


@pytest.fixture
def ig(chei_de_test: None) -> Iterator[tuple[GraphSimulat, ConectorInstagram, list[float]]]:
    g, d, pauze = GraphSimulat(), DepozitInMemorie(), []
    c = ConectorInstagram(
        app_id=APP_ID, app_secret=APP_SECRET, depozit=d, transport=g.transport, dormi=pauze.append
    )
    yield g, c, pauze


class TestConectorInstagram(ContractPublicare):
    @pytest.fixture
    def mediu(self, ig: tuple[GraphSimulat, ConectorInstagram, list[float]]) -> Mediu:
        g, c, _ = ig
        tenant, t = new_id(), g.token_nou("EAAP")
        c.depozit.pune(tenant, "instagram", Token(t, None, "", g.ig))  # type: ignore[attr-defined]
        return Mediu(c, g, tenant, dict(PACHET), token=t, adrese=g.adrese)


def test_clipul_asteapta_procesarea_fara_asteptari_reale(
    ig: tuple[GraphSimulat, ConectorInstagram, list[float]],
) -> None:
    g, c, pauze = ig
    tenant, t = new_id(), g.token_nou("EAAP")
    c.depozit.pune(tenant, "instagram", Token(t, None, "", g.ig))  # type: ignore[attr-defined]
    m = Mediu(c, g, tenant, {**PACHET, "fisier": "clienti/cz/clip.mp4", "tip_media": "video"})
    r = c.trimite(m.efect())
    assert g.ig_media[0]["tip"] == "VIDEO" and r.id_extern == g.ig_media[0]["id"]
    assert pauze == [1.0, 2.0], "două citiri „în procesare”, cu pauză crescătoare (ceas controlat)"
    assert all("/publicare/fisier/" in u for u in g.descarcate), "fișierul pleacă printr-un link semnat"


def test_limita_citita_din_endpoint_opreste_publicarea(
    ig: tuple[GraphSimulat, ConectorInstagram, list[float]],
) -> None:
    g, c, _ = ig
    tenant, t = new_id(), g.token_nou("EAAP")
    c.depozit.pune(tenant, "instagram", Token(t, None, "", g.ig))  # type: ignore[attr-defined]
    g.limita_ig = 1
    m = Mediu(c, g, tenant, dict(PACHET))
    c.trimite(m.efect())
    assert c.limite(tenant).ramase == 0
    with pytest.raises(EroareTemporara, match="limita"):
        c.trimite(m.efect(text="A doua postare."))
    assert len(g.ig_media) == 1
