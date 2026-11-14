"""F9.2 — Facebook, pagini. „Gata când”: o postare de test apare pe pagina agenției, o singură dată, iar
cererea de
App Review pleacă împreună cu înregistrarea fluxului. Graph API e SIMULAT (contract HTTP local, # SIMULAT);
pagina,
aplicația Meta și depunerea în consolă: la migrare."""

# ruff: noqa: F811
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import get_settings
from app.connectors import registru
from app.connectors.publicare.facebook import ConectorFacebook
from app.db import sesiune_agentie, sesiune_tenant
from app.operare import efecte, motor
from app.operare.efecte import autorizare
from app.publicare import aprobari, canale
from tests.integration.publicare_utile import autorizeaza, cere, efect, livrabil_stare
from tests.integration.utile_productie import fabrica_clienti, livrabil_in_publicare, om, tenant  # noqa: F401
from tests.platforme.meta import APP_ID, APP_SECRET, GraphSimulat

pytestmark = pytest.mark.db


@pytest.fixture
def graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[GraphSimulat]:
    monkeypatch.setenv("AMA_MEDIA_DIR", str(tmp_path / "media"))
    get_settings.cache_clear()
    registru.uita_tot()
    g = GraphSimulat()
    registru.inregistreaza(
        "facebook", ConectorFacebook(app_id=APP_ID, app_secret=APP_SECRET, transport=g.transport)
    )
    yield g
    registru.uita_tot()
    get_settings.cache_clear()


def test_postarea_de_test_apare_o_data_si_cererea_pleaca_cu_inregistrarea(
    tenant: uuid.UUID, om: uuid.UUID, graph: GraphSimulat
) -> None:
    text = "Cafeneaua Zorilor: de azi, cafea de specialitate."
    with autorizare.inregistreaza_fluxul(
        "facebook"
    ) as pasi:  # fluxul real, în modul de test, pe contul agenției
        url = autorizeaza(tenant, om, "facebook", graph.cod_valid())
        assert url.startswith("https://www.facebook.com/") and "pages_manage_posts" in url
        with sesiune_tenant(tenant) as db:
            m = canale.mod(db, tenant, "facebook")
            assert m.automat and m.restrans, "aplicația în test: automat doar pe pagina agenției"
        lid = livrabil_in_publicare(tenant, om, canal="facebook")
        eid = cere(tenant, lid, {"text": text, "taguri": ["cafea"]})
        assert efecte.incearca_efect(tenant, eid) == "trimis"
    # pe pagina agenției: o singură postare, cu textul aprobat
    assert [p["text"] for p in graph.postari] == [f"{text}\n\n#cafea"]
    e = efect(tenant, eid)
    assert e.id_extern == graph.postari[0]["id"] and e.link == graph.postari[0]["link"]
    assert livrabil_stare(tenant, lid) == "publicat"
    # o singură dată și când răspunsul platformei se pierde: a doua încercare întreabă întâi pagina
    lid2 = livrabil_in_publicare(tenant, om, canal="facebook")
    eid2 = cere(tenant, lid2, {"text": "Cafeneaua Zorilor: program de weekend."})
    graph.injecteaza("pierde_raspunsul")
    with pytest.raises(motor.EroareTemporara):
        efecte.incearca_efect(tenant, eid2)
    assert efecte.incearca_efect(tenant, eid2) == "trimis"
    assert [p["text"] for p in graph.postari].count("Cafeneaua Zorilor: program de weekend.") == 1
    tokenuri = graph.tokenuri
    assert all(t not in a for a in graph.adrese for t in tokenuri), "tokenul nu apare în nicio adresă"
    # cererea de App Review pleacă împreună cu înregistrarea fluxului
    rel = aprobari.salveaza_inregistrarea("meta", "pagini", pasi)
    text_inregistrare = (Path(get_settings().media_dir) / rel).read_text()
    assert "/feed" in text_inregistrare and "oauth/access_token" in text_inregistrare
    assert not any(t in text_inregistrare for t in tokenuri)
    with sesiune_agentie() as db:
        a = aprobari.trimite_cererea(db, "meta", "pagini", inregistrare=rel, utilizator_id=om)
        assert a.stare == "trimisa" and a.inregistrare == rel and a.trimisa_la is not None
    with sesiune_agentie() as db, pytest.raises(aprobari.CerereRefuzata):
        aprobari.trimite_cererea(db, "meta", "pagini", inregistrare=rel)
    with sesiune_agentie() as db:  # aplicația rămâne „în test” pentru celelalte teste
        a2 = canale.aprobare(db, "meta", "pagini")
        assert a2 is not None
        a2.stare, a2.inregistrare = "in_test", None


def test_cererea_fara_publicare_reusita_nu_pleaca(om: uuid.UUID, graph: GraphSimulat) -> None:
    rel = aprobari.salveaza_inregistrarea(
        "meta", "pagini", [{"metoda": "GET", "cale": "/v23.0/me", "status": 200}]
    )
    with sesiune_agentie() as db, pytest.raises(aprobari.CerereRefuzata, match="publicare reușită"):
        aprobari.trimite_cererea(db, "meta", "pagini", inregistrare=rel, utilizator_id=om)
    with sesiune_agentie() as db, pytest.raises(aprobari.CerereRefuzata, match="nu există"):
        aprobari.trimite_cererea(db, "meta", "pagini", inregistrare="../../etc/passwd")
