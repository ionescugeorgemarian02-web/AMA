"""F11.6 — ecranul „Învățare”. „Gata când”: aprobi o lecție și anulezi o promovare de pe telefon (din
panou, fără alt instrument). Plus: refuzurile Constituției se văd pe ecran, înghețarea, experimentele și
cine are voie să decidă."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.conturi import Rol
from app.db import sesiune_tenant
from app.invatare import Experiment, Lectie
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401

pytestmark = pytest.mark.db
LID = "11111111-1111-7111-8111-111111111111"


@pytest.fixture(autouse=True)
def _dezghetat(admin_engine: Engine) -> Iterator[None]:
    yield
    with admin_engine.begin() as c:
        c.execute(text("UPDATE invatare_stare SET inghetat = false WHERE id = 1"))


def propune(t: uuid.UUID, cheie: str, domeniu: str = "") -> uuid.UUID:
    with sesiune_tenant(t) as db:
        r = Lectie(
            tenant_id=t, cheie=cheie, domeniu_tip="canal" if domeniu else "client", domeniu=domeniu,
            text=f"Folosește mai des întrebarea în deschidere ({cheie}).",
            dovezi=[{"livrabil_id": LID, "canal": "facebook", "la_suta": 4.2}], sursa="rezultate",
        )  # fmt: skip
        db.add(r)
        db.flush()
        return r.id


def lectie(t: uuid.UUID, lid: uuid.UUID) -> Lectie:
    with sesiune_tenant(t) as db:
        r = db.get(Lectie, lid)
        assert r is not None
        db.expunge(r)
        return r


def test_aprobi_o_lectie_si_anulezi_o_promovare_din_panou(
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
    tenant: uuid.UUID,
    admin_engine: Engine,
) -> None:
    prima, a_doua, alt_domeniu = (
        propune(tenant, "prima"),
        propune(tenant, "a-doua"),
        propune(tenant, "pe-tiktok", "tiktok"),
    )
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    assert 'href="/invatare"' in client.get("/meniu").text

    h = client.get("/invatare").text
    assert "Lecții de curatoriat" in h and "întrebarea în deschidere (prima)" in h
    assert f'href="/analiza/livrabil/{LID}"' in h and "la suta: 4.2" in h, "dovezile se văd"
    jeton = csrf(client, "/invatare")

    # aprobarea
    r = client.post(f"/invatare/lectie/{prima}/aproba", data={"csrf_token": jeton}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/invatare?client={tenant}&mesaj=aprobata"
    assert lectie(tenant, prima).stare == "activa"
    h = client.get(r.headers["location"]).text
    assert "Lecția a fost aprobată" in h and "Lecții active (1)" in h and "Anulează promovarea" in h

    # Constituția: a doua promovare pe același domeniu, în aceeași săptămână, e refuzată și se vede de ce
    r = client.post(f"/invatare/lectie/{a_doua}/aproba", data={"csrf_token": jeton})
    assert r.status_code == 422 and "o promovare în ultimele 7 zile" in r.text
    assert lectie(tenant, a_doua).stare == "propusa"

    # respingerea cere motiv; fără jeton nu trece nimic
    cale = f"/invatare/lectie/{a_doua}/respinge"
    assert client.post(cale, data={"csrf_token": jeton, "motiv": ""}).status_code == 422
    assert client.post(cale, data={"motiv": "nu se potrivește"}).status_code == 403
    assert client.post(cale, data={"csrf_token": jeton, "motiv": "nu se potrivește"}, follow_redirects=False).status_code == 303  # fmt: skip
    assert lectie(tenant, a_doua).stare == "respinsa"

    # înghețarea oprește promovările, nu și retragerea
    r = client.post("/invatare/ingheata", data={"csrf_token": jeton, "activ": "1", "motiv": "verific"}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    assert "<strong>Înghețată.</strong>" in client.get("/invatare").text
    r = client.post(f"/invatare/lectie/{alt_domeniu}/aproba", data={"csrf_token": jeton})
    assert r.status_code == 422 and "înghețată" in r.text
    r = client.post(
        f"/invatare/lectie/{prima}/retrage",
        data={"csrf_token": jeton, "motiv": "a scăzut calitatea"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"].endswith("mesaj=retrasa")
    assert lectie(tenant, prima).stare == "retrasa"
    h = client.get(f"/invatare?client={tenant}").text
    assert "Lecții active (0)" in h and "<td>retrasă</td>" in h and "a scăzut calitatea" in h
    assert "<td>respinsă</td>" in h and "nu se potrivește" in h
    assert client.post("/invatare/ingheata", data={"csrf_token": jeton, "activ": "0"}, follow_redirects=False).status_code == 303  # fmt: skip
    assert "<strong>Înghețată.</strong>" not in client.get("/invatare").text

    # urma completă: fiecare decizie e în jurnal, cu omul care a luat-o
    with admin_engine.connect() as c:
        actiuni = [
            a
            for (a,) in c.execute(
                text(
                    "SELECT actiune FROM jurnal_audit WHERE tenant_id = :t AND utilizator_id IS NOT NULL "
                    "AND actiune LIKE 'invatare.%' ORDER BY creat_la, id"
                ),
                {"t": tenant},
            )
        ]
    assert actiuni == ["invatare.lectie_aprobata", "invatare.lectie_respinsa", "invatare.lectie_retrasa"]

    # adrese greșite
    assert client.post("/invatare/lectie/nu-e-id/aproba", data={"csrf_token": jeton}).status_code == 404
    assert client.post(f"/invatare/lectie/{prima}/sterge", data={"csrf_token": jeton}).status_code == 404
    assert client.get("/invatare?client=nu-e-id").status_code == 404
    assert client.get(f"/invatare?client={uuid.uuid4()}").status_code == 404


def test_experimentul_se_declara_si_se_opreste_din_panou(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float], tenant: uuid.UUID
) -> None:
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    jeton = csrf(client, "/invatare")
    date = {
        "csrf_token": jeton,
        "ipoteza": "Întrebarea în deschidere aduce mai multe interacțiuni.",
        "dimensiune": "tipar_hook",
        "varianta_a": "intrebare",
        "varianta_b": "cifra",
        "minim_pe_varianta": "10",
        "durata_maxima_zile": "45",
    }
    cale = f"/invatare/experiment/{tenant}"
    assert client.post(cale, data={**date, "minim_pe_varianta": "zece"}).status_code == 422
    assert client.post(cale, data={**date, "varianta_b": "intrebare"}).status_code == 422
    assert client.post(cale, data=date, follow_redirects=False).status_code == 303
    r = client.post(cale, data=date)
    assert r.status_code == 422 and "o schimbare o dată" in r.text
    h = client.get(f"/invatare?client={tenant}").text
    assert "Întrebarea în deschidere aduce" in h and "în curs" in h and "cel mult 45 de zile" in h
    assert "Alegerea adaptivă" in h and "Nicio postare măsurată încă." in h
    with sesiune_tenant(tenant) as db:
        eid = db.execute(text("SELECT id FROM experimente WHERE tenant_id = :t"), {"t": tenant}).scalar_one()
    opreste = f"/invatare/experiment/{eid}/opreste"
    assert client.post(opreste, data={"csrf_token": jeton, "motiv": ""}).status_code == 422
    r = client.post(opreste, data={"csrf_token": jeton, "motiv": "clientul schimbă oferta"}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    with sesiune_tenant(tenant) as db:
        e = db.get(Experiment, eid)
        assert e is not None and e.stare == "oprit"
    assert "clientul schimbă oferta" in client.get(f"/invatare?client={tenant}").text


def test_analistul_citeste_dar_nu_decide_iar_operatorul_nu_vede_ecranul(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float], tenant: uuid.UUID
) -> None:
    lid = propune(tenant, "de-citit")
    autentifica(client, fabrica_conturi(Rol.ANALIST, cu_totp=True), ceas)
    h = client.get("/invatare")
    assert h.status_code == 200 and "Starea învățării" in h.text
    assert "/invatare/ingheata" not in h.text and "Aprobă lecția" not in h.text
    jeton = csrf(client, "/invatare")
    assert client.post(f"/invatare/lectie/{lid}/aproba", data={"csrf_token": jeton}).status_code == 403
    assert client.post("/invatare/ingheata", data={"csrf_token": jeton, "activ": "1"}).status_code == 403
    assert lectie(tenant, lid).stare == "propusa"


def test_operatorul_nu_are_ecranul(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float]
) -> None:
    autentifica(client, fabrica_conturi(Rol.OPERATOR, cu_totp=True), ceas)
    assert client.get("/invatare").status_code == 403
    assert 'href="/invatare"' not in client.get("/meniu").text
