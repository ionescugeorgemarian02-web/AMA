"""Testele de contract comune ale conectorilor de publicare (F9.1). Fiecare conector le moștenește cu
platforma lui
simulată (# SIMULAT): conectorul fals în memorie, apoi Facebook, Instagram, YouTube, LinkedIn, TikTok, blogul
pe
contracte HTTP locale. Fără rețea reală și fără așteptări reale.

O clasă de test concretă definește fixture-ul `mediu` (vezi `Mediu`)."""

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit

import pytest

from app.connectors.contract import EfectDeTrimis
from app.connectors.publicare import ConectorPublicare, Limite, StarePostare
from app.ids import new_id
from app.operare.motor import EroareAutentificare, EroareDefinitiva, EroareTemporara


class Platforma(Protocol):
    def injecteaza(self, *defecte: str) -> None: ...
    def postari_publicate(self) -> list[dict[str, str]]: ...
    def expira_tokenul(self) -> None: ...
    def cod_valid(self) -> str: ...


@dataclass
class Mediu:
    conector: ConectorPublicare
    platforma: Platforma
    tenant_id: uuid.UUID
    pachet: dict[str, Any]
    stare_asteptata: StarePostare = StarePostare.PUBLICATA
    token: str = ""  # tokenul curent (nu trebuie să apară în adrese, rezultate)
    adrese: list[str] = field(default_factory=list)  # adresele cererilor văzute de platformă (dacă le expune)

    def efect(self, **payload: Any) -> EfectDeTrimis:
        lid = new_id()
        return EfectDeTrimis(
            id=new_id(),
            tenant_id=self.tenant_id,
            livrabil_id=lid,
            canal=self.conector.canal,
            versiune=1,
            tip="publicare",
            idem=f"{self.tenant_id}:{lid}:{self.conector.canal}:v1:publicare",
            payload={**self.pachet, **payload},
        )


class ContractPublicare:
    @pytest.fixture
    def mediu(self) -> Mediu:  # pragma: no cover - suprascris
        raise NotImplementedError

    def test_respecta_protocolul(self, mediu: Mediu) -> None:
        assert isinstance(mediu.conector, ConectorPublicare)
        assert mediu.conector.canal

    def test_publica_o_data_si_verifica_gaseste(self, mediu: Mediu) -> None:
        e = mediu.efect()
        assert mediu.conector.verifica(e) is None, "înainte de publicare nu există nimic"
        r = mediu.conector.trimite(e)
        assert r.id_extern and r.link.startswith("https://")
        assert len(mediu.platforma.postari_publicate()) == 1
        g = mediu.conector.verifica(e)
        assert g is not None and g.id_extern == r.id_extern
        alt = mediu.efect(text="Alt text, altă postare.")
        assert mediu.conector.verifica(alt) is None, "alt efect nu se confundă cu primul"

    def test_raspuns_pierdut_verifica_gaseste_postarea(self, mediu: Mediu) -> None:
        e = mediu.efect()
        mediu.platforma.injecteaza("pierde_raspunsul")
        with pytest.raises(EroareTemporara):
            mediu.conector.trimite(e)
        g = mediu.conector.verifica(e)
        assert g is not None, (
            "postarea făcută cu răspuns pierdut trebuie găsită (altfel executorul o dublează)"
        )
        assert len(mediu.platforma.postari_publicate()) == 1

    @pytest.mark.parametrize(
        ("defect", "eroare"),
        [
            ("temporar", EroareTemporara),
            ("timeout", EroareTemporara),
            ("autentificare", EroareAutentificare),
            ("definitiv", EroareDefinitiva),
        ],
    )
    def test_erorile_sunt_clasificate(self, mediu: Mediu, defect: str, eroare: type[Exception]) -> None:
        mediu.platforma.injecteaza(defect)
        with pytest.raises(eroare):
            mediu.conector.trimite(mediu.efect())
        assert mediu.platforma.postari_publicate() == []
        if eroare is EroareDefinitiva:
            assert not issubclass(eroare, EroareAutentificare)

    def test_token_expirat_cere_reautorizare(self, mediu: Mediu) -> None:
        mediu.platforma.expira_tokenul()
        with pytest.raises(EroareAutentificare):
            mediu.conector.trimite(mediu.efect())
        assert mediu.platforma.postari_publicate() == []

    def test_fara_cont_autorizat(self, mediu: Mediu) -> None:
        e = mediu.efect()
        strain = EfectDeTrimis(e.id, new_id(), e.livrabil_id, e.canal, 1, e.tip, e.idem, e.payload)
        with pytest.raises(EroareAutentificare):
            mediu.conector.trimite(strain)

    def test_stare_dupa_publicare(self, mediu: Mediu) -> None:
        r = mediu.conector.trimite(mediu.efect())
        assert mediu.conector.stare(mediu.tenant_id, r.id_extern) is mediu.stare_asteptata

    def test_limitele_sunt_citite_de_la_platforma(self, mediu: Mediu) -> None:
        mediu.conector.trimite(mediu.efect())
        lim = mediu.conector.limite(mediu.tenant_id)
        assert isinstance(lim, Limite) and lim.sursa, "limita are sursă (endpoint sau antet), nu e ghicită"
        assert lim.ramase is not None or lim.procent_folosit is not None

    def test_autorizarea_oauth(self, mediu: Mediu) -> None:
        url = mediu.conector.url_autorizare("stare-123", "https://ama.exemplu.test/publicare/autorizare")
        q = parse_qs(urlsplit(url).query)
        assert url.startswith("https://") and q["state"] == ["stare-123"]
        assert q["redirect_uri"] == ["https://ama.exemplu.test/publicare/autorizare"]
        t = mediu.conector.schimba_cod(
            mediu.platforma.cod_valid(), "https://ama.exemplu.test/publicare/autorizare"
        )
        assert t.acces and t.expira_la is not None and not t.expirat()
        assert t.acces not in repr(t), "tokenul nu apare în repr (jurnale)"
        with pytest.raises(EroareDefinitiva):
            mediu.conector.schimba_cod("cod-gresit", "https://ama.exemplu.test/publicare/autorizare")
        t2 = mediu.conector.reimprospateaza(t)
        assert t2.acces and t2.acces != t.acces

    def test_tokenul_nu_apare_in_adrese_sau_rezultat(self, mediu: Mediu) -> None:
        r = mediu.conector.trimite(mediu.efect())
        assert mediu.token and mediu.token not in r.link and mediu.token not in r.id_extern
        assert all(mediu.token not in a for a in mediu.adrese), "tokenul pleacă doar în antetul Authorization"
