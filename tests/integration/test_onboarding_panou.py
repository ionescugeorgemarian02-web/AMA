"""F4.4 — ecranul de onboarding din panou: operatorul completează interviul pentru client, vede brieful compus și îl
trimite spre aprobare. CSRF, permisiune, audit, brief cu goluri refuzat. Modelul este FALS (# SIMULAT)."""

# ruff: noqa: F811
import time
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.conturi import Rol
from app.db import sesiune_tenant
from app.onboarding import sesiuni
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import RASPUNSURI, ModelFals, model_fals, modele  # noqa: F401

pytestmark = pytest.mark.db
Fabrica = Callable[..., Cont]


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


def post(client: TestClient, cale: str, **date: str) -> object:
    return client.post(cale, data={**date, "csrf_token": csrf(client)}, follow_redirects=False)


def raspunde_tot(client: TestClient, tenant: uuid.UUID, suprascrie: dict[str, str] | None = None) -> None:
    raspunsuri = {**RASPUNSURI, **(suprascrie or {})}
    for _ in range(40):
        with sesiune_tenant(tenant) as db:
            s = sesiuni.sesiune_deschisa(db, tenant)
            assert s is not None
            q = sesiuni.urmatoarea(db, s.id)
            if q is None:
                return
            qid, cod = q.id, q.cod
        r = post(client, f"/onboarding/{tenant}/raspunde", intrebare_id=str(qid), raspuns=raspunsuri[cod])
        assert r.status_code == 303  # type: ignore[attr-defined]
    raise AssertionError("interviul nu s-a terminat")


def asteapta_brief(tenant: uuid.UUID) -> None:
    for _ in range(200):
        with sesiune_tenant(tenant) as db:
            s = sesiuni.sesiune_deschisa(db, tenant)
            if s is not None and s.stare == "brief_gata":
                return
        time.sleep(0.1)
    raise AssertionError("brieful nu s-a compus")


def test_fluxul_complet_din_panou_interviu_clarificare_brief_trimitere(
    client: TestClient,
    proprietar: Cont,
    tenant: uuid.UUID,
    modele: ModelFals,
    executor: None,
    admin_engine: Engine,
) -> None:
    assert (
        "Onboarding clienți" in client.get("/meniu").text
        and 'href="/onboarding"' in client.get("/meniu").text
    )
    pagina = client.get(f"/onboarding/{tenant}").text
    assert "Nu există un interviu deschis" in pagina
    assert client.post(f"/onboarding/{tenant}/porneste", data={}).status_code == 403  # fără CSRF
    r = post(client, f"/onboarding/{tenant}/porneste")
    assert r.status_code == 303  # type: ignore[attr-defined]
    pagina = client.get(f"/onboarding/{tenant}").text
    assert "Cum se numește brandul" in pagina and "0 din 11" in pagina and "<progress" in pagina
    # un răspuns vag primește o clarificare, vizibilă ca următoarea întrebare
    with sesiune_tenant(tenant) as db:
        s = sesiuni.sesiune_deschisa(db, tenant)
        assert s is not None
        q = sesiuni.urmatoarea(db, s.id)
        assert q is not None
        sid = s.id
    post(client, f"/onboarding/{tenant}/raspunde", intrebare_id=str(q.id), raspuns=RASPUNSURI["nume"])
    with sesiune_tenant(tenant) as db:
        q = sesiuni.urmatoarea(db, sid)
        assert q is not None
    post(
        client,
        f"/onboarding/{tenant}/raspunde",
        intrebare_id=str(q.id),
        raspuns="Diverse produse și multe lucruri.",
    )
    pagina = client.get(f"/onboarding/{tenant}").text
    assert "Care sunt cele două produse care se vând cel mai bine" in pagina and "clarificare" in pagina
    raspunde_tot(client, tenant)
    assert "Interviul este terminat" in client.get(f"/onboarding/{tenant}").text
    post(client, f"/onboarding/{tenant}/compune")
    asteapta_brief(tenant)
    pagina = client.get(f"/onboarding/{tenant}").text
    assert "Brieful este complet" in pagina and "Trimite brieful spre aprobare" in pagina
    assert "Ce vinde" in pagina and "Obiectiv pe 90 de zile" in pagina
    r = post(client, f"/onboarding/{tenant}/trimite")
    assert r.status_code == 303 and r.headers["location"].endswith("mesaj=trimis")  # type: ignore[attr-defined]
    with admin_engine.connect() as c:
        stare = c.execute(
            text(
                "SELECT v.stare FROM creier_versiuni v JOIN creier_intrari i ON i.id = v.intrare_id "
                "WHERE i.tenant_id = :t AND i.compartiment = 'brief'"
            ),
            {"t": tenant},
        ).scalar_one()
        audit = c.execute(
            text("SELECT count(*) FROM jurnal_audit WHERE tenant_id = :t AND actiune LIKE 'onboarding.%'"),
            {"t": tenant},
        ).scalar_one()
    assert stare == "propus" and audit >= 12  # fiecare răspuns, compunerea și deschiderea lasă o urmă


def test_brieful_cu_goluri_este_refuzat_in_panou_pana_la_corectare(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    post(client, f"/onboarding/{tenant}/porneste")
    raspunde_tot(client, tenant, {"obiectiv": "Nu știu"})
    post(client, f"/onboarding/{tenant}/compune")
    asteapta_brief(tenant)
    pagina = client.get(f"/onboarding/{tenant}").text
    assert "nu e complet și nu poate fi trimis" in pagina and "Obiectiv pe 90 de zile: gol" in pagina
    r = post(client, f"/onboarding/{tenant}/trimite")
    assert r.status_code == 422 and "câmpuri necompletate" in r.text  # type: ignore[attr-defined]
    r = post(
        client,
        f"/onboarding/{tenant}/camp",
        camp="obiectiv_90_zile",
        valoare="60 de abonamente noi în 90 de zile",
    )
    assert r.status_code == 303  # type: ignore[attr-defined]
    assert "Brieful este complet" in client.get(f"/onboarding/{tenant}").text
    assert post(client, f"/onboarding/{tenant}/trimite").status_code == 303  # type: ignore[attr-defined]


def test_analistul_citeste_dar_nu_poate_completa(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float], tenant: uuid.UUID
) -> None:
    cont = fabrica_conturi(Rol.ANALIST, cu_totp=True)
    autentifica(client, cont, ceas)
    assert client.get("/onboarding").status_code == 200
    assert post(client, f"/onboarding/{tenant}/porneste").status_code == 403  # type: ignore[attr-defined]
