"""F7.3 — portalul: cont și onboarding. „Gata când”: un client de test își face contul și parcurge interviul.
Invitația vine pe email (cutia poștală SIMULATĂ); clarificările interviului le cere modelul FALS (# SIMULAT)."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app.connectors.email import CutiePostalaSimulata
from app.conturi import Rol
from app.db import sesiune_tenant
from app.onboarding import sesiuni
from tests.integration.conftest import Cont, csrf_din, login
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401
from tests.integration.utile_site import asteapta, cutie, link_din  # noqa: F401
from tests.onboarding_utile import RASPUNSURI, ModelFals, model_fals, modele  # noqa: F401

pytestmark = pytest.mark.db
EMAIL = "patron@zorilor.example"
PAROLA = "o parolă lungă de client 42"


def activeaza_contul(client: TestClient, cutie: CutiePostalaSimulata, email: str = EMAIL) -> None:
    mesaj = asteapta(lambda: next((m for m in cutie.catre(email) if "Activează" in m.subiect), None))
    cale = urlsplit(link_din(mesaj.text, "/activare/")).path
    h = client.get(cale).text
    assert email in h and 'name="parola"' in h
    r = client.post(cale, data={"csrf_token": csrf_din(h), "parola": "scurta", "nume_afisat": "Ion"})
    assert r.status_code == 422
    r = client.post(cale, data={"csrf_token": csrf_din(client.get(cale).text), "parola": PAROLA,
                                "nume_afisat": "Ion Zorilor"}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"].startswith("/conturi/login")
    assert client.get(cale).status_code == 404  # o singură folosire


def parcurge_interviul(client: TestClient, tenant: uuid.UUID) -> None:
    r = client.post("/portal/onboarding/porneste", data={"csrf_token": csrf(client, "/portal/onboarding")},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    for _ in range(40):
        with sesiune_tenant(tenant) as db:
            s = sesiuni.sesiune_deschisa(db, tenant)
            assert s is not None
            q = sesiuni.urmatoarea(db, s.id)
            if q is None:
                break
            qid, cod, text_q = q.id, q.cod, q.text_intrebare
        h = client.get("/portal/onboarding").text
        assert text_q.split()[0] in h
        r = client.post("/portal/onboarding/raspunde", data={"csrf_token": csrf_din(h), "intrebare_id": str(qid),
                        "raspuns": RASPUNSURI[cod]}, follow_redirects=False)  # fmt: skip
        assert r.status_code == 303
    else:
        raise AssertionError("interviul nu s-a terminat")
    h = client.get("/portal/onboarding").text
    assert "Ai răspuns la toate întrebările" in h
    r = client.post("/portal/onboarding/compune", data={"csrf_token": csrf_din(h)}, follow_redirects=False)
    assert r.status_code == 303


def test_clientul_isi_face_contul_si_parcurge_interviul(
    client: TestClient, cutie: CutiePostalaSimulata, executor: None, tenant: uuid.UUID, modele: ModelFals,
    fabrica_conturi: Callable[..., Cont], ceas: dict[str, float],
) -> None:  # fmt: skip
    # agenția trimite invitația din panou
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    r = client.post(f"/onboarding/{tenant}/invita", data={"csrf_token": csrf(client), "email": EMAIL},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    client.cookies.clear()
    activeaza_contul(client, cutie)
    assert login(client, EMAIL, PAROLA).status_code == 303
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/portal"
    h = client.get("/portal").text
    assert "Ion Zorilor" in h and "Răspunde la interviu" in h and "<progress" in h
    assert client.get(f"/onboarding/{tenant}").status_code == 403  # ecranele agenției nu sunt ale clientului
    parcurge_interviul(client, tenant)
    with sesiune_tenant(tenant) as db:
        s = sesiuni.sesiune_deschisa(db, tenant)
        assert s is not None and sesiuni.progres(db, s.id).terminat
    asteapta(lambda: client.get("/portal").text.count("✓ ") >= 2)  # contul și interviul, gata


def test_linkul_invalid_si_clientul_nu_vede_alt_client(
    client: TestClient, fabrica_conturi: Callable[..., Cont], fabrica_clienti: Callable[[], uuid.UUID],
) -> None:  # fmt: skip
    assert client.get("/portal/activare/" + "x" * 40).status_code == 404
    altul = fabrica_clienti()
    cont = fabrica_conturi(Rol.CLIENT_TITULAR)
    assert login(client, cont.email, cont.parola).status_code == 303
    client.post("/portal/onboarding/porneste", data={"csrf_token": csrf(client, "/portal/onboarding")})
    with sesiune_tenant(altul) as db:
        assert sesiuni.sesiune_deschisa(db, altul) is None
    with sesiune_tenant(cont.tenant_id) as db:  # type: ignore[arg-type]
        assert sesiuni.sesiune_deschisa(db, cont.tenant_id) is not None  # type: ignore[arg-type]
