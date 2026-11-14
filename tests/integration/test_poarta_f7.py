"""Poarta F7: un client de test parcurge tot drumul, de la audit la plată și la prima aprobare.

Pașii clientului trec prin rutele reale (site, procesator, portal); restul resurselor externe sunt SIMULATE (D-007):
cutia poștală (email), procesatorul de plăți (mediul de probă din proces, webhook-uri semnate HMAC), motorul de
audit și modelele (FALSE, brandul FICTIV „Cafeneaua Zorilor”). Pașii agenției dintre interviu și primul lot
(ghid, public, piață, strategie, calendar, briefuri) folosesc lanțul de test din F4–F6, cu omul agenției."""

# ruff: noqa: F811
import re
import time
import uuid
from collections.abc import Iterator
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import continut, productie, publicare
from app.config import get_settings
from app.connectors import plati, registru
from app.connectors.email import CutiePostalaSimulata
from app.db import sesiune_agentie, sesiune_tenant
from app.finante.modele import Abonament
from app.onboarding import completare, sesiuni
from app.productie import Stare
from app.site import audit
from app.site.modele import Lead
from tests.continut_utile import model_postari
from tests.integration import lant_onboarding
from tests.integration.conftest import csrf_din, login
from tests.integration.lant_continut import cu_briefuri, fara_cereri_ramase  # noqa: F401
from tests.integration.test_portal_cont import PAROLA, activeaza_contul, parcurge_interviul
from tests.integration.utile_productie import om  # noqa: F401
from tests.integration.utile_site import asteapta, cutie, link_din  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fara_cereri_ramase")]
SECRET = "secret-de-proba-webhook-poarta-f7"  # pragma: allowlist secret
EMAIL = "poarta@zorilor.example"


@pytest.fixture
def procesator(
    monkeypatch: pytest.MonkeyPatch, cutie: CutiePostalaSimulata
) -> Iterator[plati.ProcesatorSimulat]:
    monkeypatch.setenv("AMA_PLATI_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()
    p = plati.ProcesatorSimulat(secret=SECRET)
    registru.inregistreaza_sistem(plati.TIP, p)
    yield p
    get_settings.cache_clear()


def cale(text: str, fragment: str) -> str:
    return urlsplit(link_din(text, fragment)).path


def test_poarta_f7_de_la_audit_la_plata_si_la_prima_aprobare(
    client: TestClient, cutie: CutiePostalaSimulata, procesator: plati.ProcesatorSimulat, executor: None,
    om: uuid.UUID, modele: ModelFals, monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    # 1. Auditul gratuit, cu opt-in dublu
    h = client.get("/site/audit").text
    r = client.post("/site/audit", data={"csrf_token": csrf_din(h), "firma": "Cafeneaua Zorilor",
                    "site_url": "https://zorilor.example", "email": EMAIL, "acord": "da",
                    "t": audit.jeton_formular(time.time() - 10)})  # fmt: skip
    assert r.status_code == 200
    confirmare = asteapta(lambda: next(iter(cutie.catre(EMAIL)), None))
    assert client.get(cale(confirmare.text, "/audit/confirma/")).status_code == 200
    raport = asteapta(lambda: next((m for m in cutie.catre(EMAIL) if "Raportul" in m.subiect), None))
    h = client.get(cale(raport.text, "/audit/raport/")).text
    assert "Trei lucruri de făcut" in h and "Alege pachetul" in h
    # 2. Pachetul și plata, pe pagina procesatorului (mediul de probă)
    m = re.search(r'href="(/site/inscriere\?raport=[^"]+)"', h)
    assert m is not None
    h = client.get(m.group(1)).text
    assert 'value="Cafeneaua Zorilor"' in h and f'value="{EMAIL}"' in h
    jeton_raport = h.split('name="raport" value="')[1].split('"')[0]
    r = client.post("/site/inscriere", data={"csrf_token": csrf_din(h), "firma": "Cafeneaua Zorilor", "email": EMAIL,
                    "plan": "start", "raport": jeton_raport, "acord": "da", "t": audit.jeton_formular(time.time() - 10)},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    pagina_plata = r.headers["location"]
    asteapta(lambda: "Plătește" in client.get(pagina_plata).text)
    [sub] = procesator.abonamente
    for corp, antete in procesator.plateste(sub):
        assert client.post("/facturare/webhook", content=corp, headers=antete).json()["rezultat"] == "aplicat"
    with sesiune_agentie() as db:
        a = db.execute(select(Abonament).where(Abonament.email_facturare == EMAIL)).scalar_one()
        lead = db.execute(select(Lead).where(Lead.email == EMAIL)).scalar_one()
        tenant = a.tenant_id
        assert a.stare == "activ" and lead.stare == "client" and lead.tenant_id == tenant
    # 3. Contul din linkul de activare primit după plată, apoi interviul din portal
    client.cookies.clear()
    activeaza_contul(client, cutie, EMAIL)
    assert login(client, EMAIL, PAROLA).status_code == 303
    assert client.get("/", follow_redirects=False).headers["location"] == "/portal"
    parcurge_interviul(client, tenant)

    def brief_gata() -> bool:
        with sesiune_tenant(tenant) as db:
            s = sesiuni.sesiune_deschisa(db, tenant)
            return s is not None and s.stare == "brief_gata"

    asteapta(brief_gata, secunde=30)
    # 4. Agenția trimite brieful spre aprobare; clientul îl aprobă din portal (Creierul de brand)
    with sesiune_tenant(tenant, om) as db:
        s = sesiuni.sesiune_deschisa(db, tenant)
        assert s is not None
        iid, nr = completare.trimite_spre_aprobare(db, s.id, utilizator_id=om)
    h = client.get("/portal/creier").text
    assert "de aprobat" in h
    r = client.post(f"/portal/creier/{iid}/aproba", data={"csrf_token": csrf_din(h), "versiune": nr},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    # 5. Agenția (lanțul F4–F6, model FALS): ghid, public, piață, strategie, calendar, briefuri; primul lot
    monkeypatch.setattr(
        lant_onboarding.t_ghid, "brief_aprobat", lambda t, o: None
    )  # brieful e deja aprobat de client
    cal, _ = cu_briefuri(tenant, om, modele)
    model_postari(modele)
    with sesiune_tenant(tenant) as db:
        lids = [
            i.livrabil_id for i in continut.calendar.intrari(db, cal) if i.tip == "postare" and i.livrabil_id
        ][:2]
    for lid in lids:
        assert continut.pipeline.produ(tenant, lid) == Stare.ASTEAPTA_APROBARE.value
    # 6. Prima aprobare: clientul aprobă lotul de pe telefon
    h = client.get("/portal/aprobari").text
    assert f"Aprobă tot lotul ({len(lids)})" in h
    cereri = [x.split('"')[0] for x in h.split('name="cerere" value="')[1:]]
    r = client.post(
        "/portal/aprobari/lot", data={"csrf_token": csrf_din(h), "cerere": cereri}, follow_redirects=False
    )
    assert r.status_code == 303
    with sesiune_tenant(tenant) as db:
        for lid in lids:
            lv = productie.citeste(db, lid)
            assert lv is not None and lv.stare == Stare.PROGRAMAT.value
            assert publicare.asistata.ale_livrabilului(db, lid)
    h = client.get("/portal").text
    assert "✓ Primul lot de conținut spre aprobare" in h and "✓ Răspunde la interviu" in h
    assert "activ" in client.get("/portal/cont").text
