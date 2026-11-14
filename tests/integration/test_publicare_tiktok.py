"""F9.6 — TikTok. „Gata când”: fluxul respectă regulile lor, cererea de audit este trimisă cu înregistrarea
fluxului și starea ei se vede în panou. Înainte de audit: ciornă în aplicație; după: postare directă doar cu
previzualizare și consimțământ (vizibilitatea aleasă de om, fără valoare implicită). Content Posting API e
SIMULAT (# SIMULAT)."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app import validare
from app.config import get_settings
from app.connectors import registru
from app.connectors.contract import StarePostare
from app.connectors.publicare.tiktok import ConectorTiktok
from app.conturi import Rol
from app.db import sesiune_agentie, sesiune_tenant
from app.operare import efecte
from app.operare.efecte import autorizare
from app.publicare import aprobari, consimtamant
from tests.integration.conftest import Cont
from tests.integration.publicare_utile import autorizeaza, cere, efect, pune_aprobarea
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, livrabil_in_publicare, om, tenant  # noqa: F401
from tests.platforme.tiktok import CLIENT_KEY, CLIENT_SECRET, TiktokSimulat

pytestmark = pytest.mark.db


@pytest.fixture
def tt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, client: TestClient) -> Iterator[TiktokSimulat]:
    monkeypatch.setenv("AMA_MEDIA_DIR", str(tmp_path / "media"))
    get_settings.cache_clear()
    registru.uita_tot()
    s = TiktokSimulat()
    s.descarca = lambda url: client.get(urlsplit(url).path).status_code
    registru.inregistreaza(
        "tiktok",
        ConectorTiktok(
            client_key=CLIENT_KEY, client_secret=CLIENT_SECRET, transport=s.transport, dormi=lambda x: None
        ),
    )
    yield s
    registru.uita_tot()
    get_settings.cache_clear()


def test_ciorna_inainte_de_audit_apoi_postare_directa_cu_consimtamant(
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
    tenant: uuid.UUID,
    om: uuid.UUID,
    tt: TiktokSimulat,
    media_tiktok: Callable[[uuid.UUID], str],
) -> None:
    with autorizare.inregistreaza_fluxul("tiktok") as pasi:
        autorizeaza(tenant, om, "tiktok", tt.cod_valid())
        lid = livrabil_in_publicare(tenant, om, canal="tiktok")
        rel = media_tiktok(tenant)
        eid = cere(
            tenant, lid, {"text": "Cafeneaua Zorilor: latte art.", "fisier": rel, "mod_tiktok": "ciorna"}
        )
        assert efecte.incearca_efect(tenant, eid) == "trimis"
    assert len(tt.ciorne) == 1 and tt.postari == [], "înainte de audit: ciornă în aplicație, nimic public"
    assert (
        autorizare.stare_postare(tenant, "tiktok", str(efect(tenant, eid).id_extern)) is StarePostare.CIORNA
    )
    # cererea de audit, cu înregistrarea fluxului; starea se vede în panou
    inr = aprobari.salveaza_inregistrarea("tiktok", "publicare", pasi)
    with sesiune_agentie() as db:
        assert (
            aprobari.trimite_cererea(db, "tiktok", "publicare", inregistrare=inr, utilizator_id=om).stare
            == "trimisa"
        )
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    lid2 = livrabil_in_publicare(tenant, om, canal="tiktok")
    with sesiune_tenant(tenant) as db:
        validare.continut.scrie(db, lid2, text="Cafeneaua Zorilor: cold brew.", autor="test")
    pagina = client.get(f"/publicare/api/tiktok/{lid2}").text
    assert "Trimisă, în analiză" in pagina and "Cafeneaua Zorilor" in pagina
    assert (
        'value="SELF_ONLY" required>' in pagina
        and "checked" not in pagina.split("Interacțiuni")[0].split("Cine vede")[1]
    ), "nicio vizibilitate aleasă implicit"
    # după audit: postare directă, doar cu consimțământ explicit și vizibilitatea aleasă
    with sesiune_agentie() as db:
        aprobari.decide(db, "tiktok", "publicare", aprobata=True, utilizator_id=om)
    tt.auditat = True
    jeton = csrf(client, f"/publicare/api/tiktok/{lid2}")
    r = client.post(f"/publicare/api/tiktok/{lid2}", data={"csrf_token": jeton, "de_acord": "true"})
    assert r.status_code == 422 and "alege vizibilitatea" in r.text
    r = client.post(
        f"/publicare/api/tiktok/{lid2}",
        data={
            "csrf_token": jeton,
            "vizibilitate": "PUBLIC_TO_EVERYONE",
            "fara_duet": "true",
            "de_acord": "true",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    with sesiune_tenant(tenant) as db:
        c = consimtamant.al_versiunii(db, lid2, 1, "tiktok")
        assert (
            c is not None and c.optiuni["vizibilitate"] == "PUBLIC_TO_EVERYONE" and c.optiuni["fara_stitch"]
        )
        cons = consimtamant.pentru_pachet(c)
    eid2 = cere(
        tenant,
        lid2,
        {
            "text": "Cafeneaua Zorilor: cold brew.",
            "fisier": rel,
            "mod_tiktok": "direct",
            "consimtamant": cons,
            "eticheta_ai": False,
        },
    )
    assert efecte.incearca_efect(tenant, eid2) == "trimis"
    assert [(p["privacy"], p["is_aigc"]) for p in tt.postari] == [("PUBLIC_TO_EVERYONE", False)]
    assert (
        autorizare.stare_postare(tenant, "tiktok", str(efect(tenant, eid2).id_extern))
        is StarePostare.PUBLICATA
    )
    pune_aprobarea("tiktok", "publicare", "in_test")


@pytest.fixture
def media_tiktok() -> Callable[[uuid.UUID], str]:
    def f(tenant: uuid.UUID) -> str:
        rel = f"clienti/{tenant}/latte.mp4"
        cale = Path(get_settings().media_dir) / rel
        cale.parent.mkdir(parents=True, exist_ok=True)
        cale.write_bytes(b"\x00\x00\x00\x18ftypmp42 latte")
        return rel

    return f
