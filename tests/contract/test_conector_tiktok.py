"""F9.6 — conectorul TikTok trece suita de contract (postare directă, după audit, cu consimțământ), pe Content
Posting API simulat (# SIMULAT); ciorna înainte de audit; refuzul fără consimțământ."""

from collections.abc import Iterator

import pytest

from app.connectors.contract import StarePostare, Token
from app.connectors.publicare import DepozitInMemorie
from app.connectors.publicare.tiktok import ConectorTiktok
from app.ids import new_id
from app.operare.motor import EroareDefinitiva
from tests.contract.contract_publicare import ContractPublicare, Mediu
from tests.platforme.tiktok import CLIENT_KEY, CLIENT_SECRET, TiktokSimulat

CONSIMTAMANT = {"id": "c-1", "dat_de": "om-1", "vizibilitate": "PUBLIC_TO_EVERYONE"}
PACHET = {"text": "Cafeneaua Zorilor: latte art.", "fisier": "clienti/cz/clip.mp4", "eticheta_ai": False}


@pytest.fixture
def tt(chei_de_test: None) -> Iterator[tuple[TiktokSimulat, ConectorTiktok, Token]]:
    s, d, pauze = TiktokSimulat(), DepozitInMemorie(), []
    c = ConectorTiktok(
        client_key=CLIENT_KEY,
        client_secret=CLIENT_SECRET,
        depozit=d,
        transport=s.transport,
        dormi=pauze.append,
    )
    yield s, c, Token(s.token_nou("act"), None, "rft.vechi", "cafeneauazorilor")


def mediu_tt(s: TiktokSimulat, c: ConectorTiktok, t: Token, **pachet: object) -> Mediu:
    tenant = new_id()
    c.depozit.pune(tenant, "tiktok", t)  # type: ignore[attr-defined]
    return Mediu(c, s, tenant, {**PACHET, **pachet}, token=t.acces, adrese=s.adrese)


class TestConectorTiktokDirect(ContractPublicare):
    @pytest.fixture
    def mediu(self, tt: tuple[TiktokSimulat, ConectorTiktok, Token]) -> Mediu:
        s, c, t = tt
        s.auditat = True
        return mediu_tt(s, c, t, mod_tiktok="direct", consimtamant=CONSIMTAMANT)


def test_ciorna_inainte_de_audit(tt: tuple[TiktokSimulat, ConectorTiktok, Token]) -> None:
    s, c, t = tt
    m = mediu_tt(s, c, t, mod_tiktok="ciorna")
    r = c.trimite(m.efect())
    assert len(s.ciorne) == 1 and s.postari == []
    assert c.stare(m.tenant_id, r.id_extern) is StarePostare.CIORNA


def test_postarea_directa_cere_consimtamant_si_vizibilitate_permisa(
    tt: tuple[TiktokSimulat, ConectorTiktok, Token],
) -> None:
    s, c, t = tt
    m = mediu_tt(s, c, t, mod_tiktok="direct")
    with pytest.raises(EroareDefinitiva, match="consimțământul"):
        c.trimite(m.efect())
    with pytest.raises(EroareDefinitiva, match="nu mai este permisă"):  # neauditat: doar SELF_ONLY
        c.trimite(m.efect(consimtamant=CONSIMTAMANT))
    c.trimite(m.efect(consimtamant={**CONSIMTAMANT, "vizibilitate": "SELF_ONLY"}, eticheta_ai=True))
    assert s.postari[0]["privacy"] == "SELF_ONLY" and s.postari[0]["is_aigc"] is True
