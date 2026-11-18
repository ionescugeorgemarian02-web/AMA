"""F12.6 — generatorul de oferte. „Gata când”: o ofertă pornește din audit și din pachete și ajunge la tine
spre aprobare. Motorul de audit și cutia poștală sunt SIMULATE."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable, Iterator
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select

from app.connectors.email import CutiePostalaSimulata
from app.conturi import Rol
from app.crm import Oferta, calificare, oferte, registru
from app.db import sesiune_agentie
from app.finante import planuri
from app.site import audit as site_audit
from tests.integration.conftest import Cont
from tests.integration.test_site_audit import date as date_formular
from tests.integration.utile_crm import curata_crm
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import om  # noqa: F401
from tests.integration.utile_site import asteapta, cutie, link_din  # noqa: F401

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _curat(admin_engine: Engine) -> Iterator[None]:
    curata_crm(admin_engine)
    yield
    curata_crm(admin_engine)


def lead_cu_audit(client: TestClient, cutie: CutiePostalaSimulata, adresa: str) -> uuid.UUID:
    assert client.post("/site/audit", data=date_formular(client, email=adresa)).status_code == 200
    [confirmare] = asteapta(lambda: cutie.catre(adresa))
    assert client.get(urlsplit(link_din(confirmare.text, "/audit/confirma/")).path).status_code == 200
    with sesiune_agentie() as db:
        [(lead, _, _)] = registru.lista(db)
        lead_id, site_id = lead.id, lead.lead_site_id
    assert site_id is not None

    def gata() -> bool | None:
        with sesiune_agentie() as db:
            return site_audit.raport_pentru_lead(db, site_id) is not None or None

    asteapta(gata)
    return lead_id


def test_oferta_porneste_din_audit_si_din_pachete_si_ajunge_la_tine_spre_aprobare(
    client: TestClient, cutie: CutiePostalaSimulata, executor: None, fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
) -> None:  # fmt: skip
    adresa = f"oferta-{uuid.uuid4().hex[:8]}@zorilor.example"
    lead_id = lead_cu_audit(client, cutie, adresa)
    with sesiune_agentie() as db:
        calificare.califica(
            db, lead_id, {"nisa": "horeca", "buget": "3000_10000", "termen": "imediat", "decident": "da"}
        )
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    jeton = csrf(client, f"/crm/lead/{lead_id}")
    assert "Pregătește oferta" in client.get(f"/crm/lead/{lead_id}").text
    r = client.post(f"/crm/lead/{lead_id}/oferta", data={"csrf_token": jeton}, follow_redirects=False)
    assert r.status_code == 303
    r2 = client.post(f"/crm/lead/{lead_id}/oferta", data={"csrf_token": jeton})
    assert r2.status_code == 422 and "deja o ofertă" in r2.text, "o singură ofertă de aprobat pe lead"

    crestere = planuri.PLANURI["crestere"]
    h = client.get("/crm/oferte").text
    assert "Cafeneaua Zorilor" in h and f"{crestere.nume}, {crestere.pret_lunar} lei/lună" in h, (
        "pachetul după buget"
    )
    assert "Oferta principală apare abia pe a doua pagină." in h, "constatările vin din audit"
    assert "Aprobă și trimite" in h and "de aprobat" in h
    assert not [m for m in cutie.catre(adresa) if m.subiect.startswith("Oferta pentru")], (
        "nimic fără decizia ta"
    )
    with sesiune_agentie() as db:
        [o] = db.scalars(select(Oferta).where(Oferta.lead_id == lead_id))
        assert o.verificari["trece"] and o.stare == "de_aprobat" and o.setup == planuri.SETUP

    r = client.post(f"/crm/oferte/{o.id}/aproba", data={"csrf_token": jeton}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("mesaj=aprobata")
    [m] = asteapta(lambda: [x for x in cutie.catre(adresa) if x.subiect.startswith("Oferta pentru")] or None)
    assert f"Preț: {crestere.pret_lunar} lei pe lună" in m.text and "Ce am găsit în audit:" in m.text
    assert client.post(f"/crm/oferte/{o.id}/aproba", data={"csrf_token": jeton}).status_code == 422
    with sesiune_agentie() as db:
        fisa = registru.fisa(db, lead_id)
        assert fisa is not None and fisa["lead"].etapa == "oferta_trimisa"


def test_fara_audit_nu_exista_oferta_verificarile_si_respingerea(om: uuid.UUID) -> None:
    with sesiune_agentie() as db:
        lead, _ = registru.primeste(
            db, email="dan@recomandat.example", firma="Firma lui Dan", sursa="recomandare"
        )
        with pytest.raises(registru.CrmRefuzat, match="pornește din audit"):
            oferte.genereaza(db, lead.id)
        raport = {"rezumat": "Site bun.", "constatari": ["Lipsește prețul."], "recomandari": ["Pune prețul."]}
        o = oferte.genereaza(db, lead.id, raport=raport)
        assert o.pachet == "crestere" and o.stare == "de_aprobat", "fără calificare: pachetul implicit"
        with pytest.raises(registru.CrmRefuzat, match="de ce"):
            oferte.respinge(db, o.id, utilizator_id=om, motiv="")
        oferte.respinge(db, o.id, utilizator_id=om, motiv="Prețul trebuie discutat întâi în apel.")
        assert o.stare == "respinsa"
        blocata = oferte.genereaza(
            db, lead.id, raport={**raport, "recomandari": ["Vă garantăm 100% mai mulți clienți."]}
        )
        assert blocata.stare == "blocata" and not blocata.verificari["fara_promisiuni_garantate"]
    c = oferte.compune("X", {"constatari": []}, "pro")
    assert not oferte.verifica(c)["constatari_din_audit"]
    assert oferte.alege_pachet("peste_10000") == "pro" and oferte.alege_pachet("1000_3000") == "start"


def test_operatorul_nu_vede_ofertele(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float]
) -> None:
    autentifica(client, fabrica_conturi(Rol.OPERATOR, cu_totp=True), ceas)
    assert client.get("/crm/oferte").status_code == 403
