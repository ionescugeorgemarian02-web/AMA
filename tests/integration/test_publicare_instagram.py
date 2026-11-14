"""F9.3 — Instagram. „Gata când”: o imagine și un clip apar pe contul agenției, iar permisiunea de publicare este
cerută în App Review. Fișierele pleacă prin linkuri semnate care expiră, servite de aplicație; limita se citește
din endpoint. Graph API e SIMULAT (contract HTTP local, # SIMULAT): contul real și App Review, la migrare."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.connectors import registru
from app.connectors.publicare.instagram import ConectorInstagram
from app.db import sesiune_agentie
from app.operare import efecte
from app.operare.efecte import autorizare
from app.publicare import aprobari, canale, linkuri
from tests.integration.publicare_utile import autorizeaza, cere, livrabil_stare
from tests.integration.utile_productie import fabrica_clienti, livrabil_in_publicare, om, tenant  # noqa: F401
from tests.platforme.meta import APP_ID, APP_SECRET, GraphSimulat

pytestmark = pytest.mark.db


@pytest.fixture
def media(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("AMA_MEDIA_DIR", str(tmp_path / "media"))
    get_settings.cache_clear()
    yield tmp_path / "media"
    get_settings.cache_clear()


@pytest.fixture
def graph(media: Path, client: TestClient) -> Iterator[GraphSimulat]:
    registru.uita_tot()
    g = GraphSimulat()
    g.descarca = lambda url: client.get(urlsplit(url).path).status_code  # Instagram aduce fișierul de la noi
    c = ConectorInstagram(app_id=APP_ID, app_secret=APP_SECRET, transport=g.transport, dormi=lambda s: None)
    registru.inregistreaza("instagram", c)
    yield g
    registru.uita_tot()


def fisier(media: Path, tenant: uuid.UUID, nume: str, corp: bytes) -> str:
    rel = f"clienti/{tenant}/{nume}"
    (media / rel).parent.mkdir(parents=True, exist_ok=True)
    (media / rel).write_bytes(corp)
    return rel


def test_imaginea_si_clipul_apar_iar_permisiunea_e_ceruta(
    tenant: uuid.UUID, om: uuid.UUID, graph: GraphSimulat, media: Path, client: TestClient
) -> None:
    imagine = fisier(media, tenant, "croissant.jpg", b"\xff\xd8\xff\xe0 imagine de proba")
    clip = fisier(media, tenant, "latte.mp4", b"\x00\x00\x00\x18ftypmp42 clip de proba")
    with autorizare.inregistreaza_fluxul("instagram") as pasi:
        autorizeaza(tenant, om, "instagram", graph.cod_valid())
        pub = []
        for rel, tip, text in (
            (imagine, "imagine", "Croissant cu unt, proaspăt."),
            (clip, "video", "Latte art."),
        ):
            lid = livrabil_in_publicare(tenant, om, canal="instagram")
            eid = cere(tenant, lid, {"text": f"Cafeneaua Zorilor: {text}", "fisier": rel, "tip_media": tip})
            assert efecte.incearca_efect(tenant, eid) == "trimis"
            pub.append(lid)
    assert [(m["tip"], m["text"]) for m in graph.ig_media] == [
        ("IMAGE", "Cafeneaua Zorilor: Croissant cu unt, proaspăt."),
        ("VIDEO", "Cafeneaua Zorilor: Latte art."),
    ], "o imagine și un clip, fiecare o singură dată, pe contul agenției"
    assert all(livrabil_stare(tenant, lid) == "publicat" for lid in pub)
    # fișierele au plecat prin linkuri semnate, servite de aplicație; modificate sau expirate nu mai merg
    assert len(graph.descarcate) == 2 and all("/publicare/fisier/" in u for u in graph.descarcate)
    cale = urlsplit(graph.descarcate[0]).path
    assert client.get(cale).content == (media / imagine).read_bytes()
    assert client.get(cale[:-2] + ("AA" if not cale.endswith("AA") else "BB")).status_code == 404
    vechi = linkuri.jeton(imagine, valabil_sec=60, acum=dt.datetime.now(dt.UTC) - dt.timedelta(hours=1))
    assert client.get(linkuri.PREFIX + vechi).status_code == 404
    assert client.get(linkuri.PREFIX + linkuri.jeton("../../etc/passwd")).status_code == 404
    lim = autorizare.limite(tenant, "instagram")
    assert lim.sursa == "endpointul content_publishing_limit" and (lim.ramase, lim.total) == (98, 100)
    # permisiunea de publicare cerută în App Review, cu înregistrarea fluxului
    rel = aprobari.salveaza_inregistrarea("meta", "instagram", pasi)
    with sesiune_agentie() as db:
        a = aprobari.trimite_cererea(db, "meta", "instagram", inregistrare=rel, utilizator_id=om)
        assert a.stare == "trimisa" and a.inregistrare == rel
        a.stare, a.inregistrare = "in_test", None
        assert canale.cerinta("instagram") == ("meta", "instagram")
