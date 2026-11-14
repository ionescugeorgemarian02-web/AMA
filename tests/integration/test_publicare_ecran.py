"""F9.10 — ecranul „Publicare”. „Gata când”: vezi starea fiecărei aprobări API și poți trece un canal pe
asistat. Plus reautorizarea din panou (OAuth: platforma întoarce omul cu codul). Platforma e FALSĂ (#
SIMULAT)."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable, Iterator
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.connectors import registru
from app.connectors.publicare import DepozitBaza
from app.connectors.publicare.fals import ConectorFalsPublicare, PlatformaFalsa
from app.conturi import Rol
from app.db import sesiune_tenant
from app.publicare import canale
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401

pytestmark = pytest.mark.db


@pytest.fixture
def platforma() -> Iterator[PlatformaFalsa]:
    registru.uita_tot()
    p = PlatformaFalsa()
    registru.inregistreaza("facebook", ConectorFalsPublicare(p, DepozitBaza(), canal="facebook"))
    yield p
    registru.uita_tot()


def test_starea_aprobarilor_si_trecerea_pe_asistat(
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
    tenant: uuid.UUID,
    om: uuid.UUID,
    platforma: PlatformaFalsa,
) -> None:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    with sesiune_tenant(tenant) as db:
        canale.configureaza(db, tenant, "facebook", nume="Cafeneaua Zorilor", cont_agentie=True)
    # reautorizarea din panou: spre platformă, apoi înapoi cu codul
    r = client.post(
        f"/publicare/canale/{tenant}/facebook/autorizeaza",
        data={"csrf_token": csrf(client, "/publicare/canale")},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"].startswith("https://platforma.exemplu.test/oauth")
    stare = parse_qs(urlsplit(r.headers["location"]).query)["state"][0]
    assert stare.split(".")[1] == str(tenant)
    r = client.get(
        f"/publicare/autorizare?code={platforma.cod_valid()}&state={stare}", follow_redirects=False
    )
    assert r.status_code == 303 and canale.token_pentru(tenant, "facebook") is not None
    r = client.get(f"/publicare/autorizare?code=x&state={stare}")
    assert r.status_code == 422, "aceeași stare nu se folosește de două ori"
    # starea fiecărei aprobări API
    h = client.get("/publicare/canale").text
    for platforma_, permisiune in (
        ("meta", "pagini"),
        ("meta", "instagram"),
        ("google", "youtube"),
        ("linkedin", "profil"),
        ("linkedin", "pagina"),
        ("tiktok", "publicare"),
    ):
        assert f"<td>{platforma_}</td><td>{permisiune}</td>" in h
    assert "Mod de test (doar conturile agenției)" in h and "Aprobată" in h
    assert "automat, în test" in h and "Trece pe asistat" in h
    # trecerea pe asistat
    r = client.post(
        f"/publicare/canale/{tenant}/facebook/mod",
        data={"csrf_token": csrf(client, "/publicare/canale"), "mod": "asistat"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    h = client.get("/publicare/canale?mesaj=asistat").text
    assert "trecut pe asistat de un om" in h and "Înapoi pe automat" in h
    with sesiune_tenant(tenant) as db:
        assert canale.mod(db, tenant, "facebook").mod is canale.Mod.ASISTAT
    r = client.post(
        f"/publicare/canale/{tenant}/facebook/mod",
        data={"csrf_token": csrf(client, "/publicare/canale"), "mod": "automat"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with sesiune_tenant(tenant) as db:
        assert canale.mod(db, tenant, "facebook").automat
    assert client.post(f"/publicare/canale/{tenant}/facebook/mod", data={"mod": "asistat"}).status_code == 403
