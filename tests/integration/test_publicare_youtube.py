"""F9.4 — YouTube. „Gata când”: un clip este public după audit sau privat înainte, cu starea afișată corect,
iar cererea de audit este trimisă. Câmpul de conținut modificat sau sintetic vine din eticheta AI; costul în
unități se numără în baza de date, pe ziua Pacific (ceas controlat). YouTube Data API e SIMULAT (contract
HTTP local)."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import get_settings
from app.connectors import registru
from app.connectors.contract import ETICHETE_STARE, StarePostare
from app.connectors.publicare.youtube import ConectorYoutube, costuri, zi_pacific
from app.db import sesiune_agentie, sesiune_tenant
from app.operare import efecte
from app.operare.efecte import autorizare
from app.publicare import aprobari, canale, cote
from tests.integration.publicare_utile import autorizeaza, cere, efect, pune_aprobarea
from tests.integration.utile_productie import fabrica_clienti, livrabil_in_publicare, om, tenant  # noqa: F401
from tests.platforme.google import CLIENT_ID, CLIENT_SECRET, YoutubeSimulat

pytestmark = pytest.mark.db
ACUM = dt.datetime.now(dt.UTC).replace(microsecond=0)  # ceas fix pe durata testului


@pytest.fixture
def yt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[YoutubeSimulat]:
    monkeypatch.setenv("AMA_MEDIA_DIR", str(tmp_path / "media"))
    get_settings.cache_clear()
    registru.uita_tot()
    y = YoutubeSimulat()
    c = ConectorYoutube(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        transport=y.transport,
        ceas=lambda: ACUM,
        costuri_unitati=costuri("videos.insert=1600,videos.list=1,channels.list=1"),
    )
    registru.inregistreaza("youtube", c)
    yield y
    registru.uita_tot()
    get_settings.cache_clear()


def clip(tenant: uuid.UUID, om: uuid.UUID, nume: str, titlu: str) -> tuple[uuid.UUID, uuid.UUID]:
    rel = f"clienti/{tenant}/{nume}"
    cale = Path(get_settings().media_dir) / rel
    cale.parent.mkdir(parents=True, exist_ok=True)
    cale.write_bytes(b"\x00\x00\x00\x18ftypmp42" + nume.encode())
    with sesiune_tenant(tenant) as db:
        m = canale.mod(db, tenant, "youtube")
    assert m.automat
    lid = livrabil_in_publicare(tenant, om, canal="youtube")
    pachet = {
        "text": f"Cafeneaua Zorilor: {titlu}.",
        "titlu": titlu,
        "fisier": rel,
        "eticheta_ai": True,
        "vizibilitate": "privat" if m.restrans else "public",
    }
    return lid, cere(tenant, lid, pachet)


def test_privat_inainte_de_audit_public_dupa_cu_starea_afisata(
    tenant: uuid.UUID, om: uuid.UUID, yt: YoutubeSimulat
) -> None:
    inainte = cote.consumat("youtube", zi_pacific(ACUM))
    with autorizare.inregistreaza_fluxul("youtube") as pasi:
        url = autorizeaza(tenant, om, "youtube", yt.cod_valid())
        assert "access_type=offline" in url and "youtube.upload" in url
        _, e1 = clip(tenant, om, "flat-white.mp4", "Flat white în 30 de secunde")
        assert efecte.incearca_efect(tenant, e1) == "trimis"
    v1 = efect(tenant, e1).id_extern
    assert v1 is not None and yt.postari[0]["sintetic"] is True, (
        "eticheta AI → conținut modificat sau sintetic"
    )
    s1 = autorizare.stare_postare(tenant, "youtube", v1)
    assert s1 is StarePostare.PRIVATA and ETICHETE_STARE[s1] == "Privată (până la audit)"
    # cererea de audit, cu înregistrarea fluxului
    rel = aprobari.salveaza_inregistrarea("google", "youtube", pasi)
    with sesiune_agentie() as db:
        assert (
            aprobari.trimite_cererea(db, "google", "youtube", inregistrare=rel, utilizator_id=om).stare
            == "trimisa"
        )
        aprobari.decide(db, "google", "youtube", aprobata=True, observatii="audit trecut", utilizator_id=om)
    yt.auditat = True
    _, e2 = clip(tenant, om, "cold-brew.mp4", "Cold brew de casă")
    assert efecte.incearca_efect(tenant, e2) == "trimis"
    v2 = efect(tenant, e2).id_extern
    assert v2 is not None
    s2 = autorizare.stare_postare(tenant, "youtube", v2)
    assert s2 is StarePostare.PUBLICATA and ETICHETE_STARE[s2] == "Publică"
    # costul în unități, numărat în bază pe ziua Pacific: două încărcări, două citiri de stare, canalul la
    # OAuth
    assert cote.consumat("youtube", zi_pacific(ACUM)) - inainte == 2 * 1600 + 2 + 1
    lim = autorizare.limite(tenant, "youtube")
    assert lim.total == 10_000 and lim.ramase == 10_000 - cote.consumat("youtube", zi_pacific(ACUM))
    pune_aprobarea("google", "youtube", "in_test")
