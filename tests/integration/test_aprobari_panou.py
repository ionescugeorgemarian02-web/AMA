"""F2.8 — punctul minim din panou pentru aprobări: lista și două acțiuni, cu CSRF, permisiune și audit."""

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app import productie
from app.conturi import Rol
from app.db import sesiune_tenant
from app.ids import new_id
from app.productie import aprobari
from app.productie.reguli_aprobare import Decident
from app.productie.stari import Stare
from tests.integration.conftest import Cont, login
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import livrabil, muta, stare

pytestmark = pytest.mark.db
Fabrica = Callable[..., Cont]


@pytest.fixture(autouse=True)
def _fara_cereri_ramase(admin_engine: Engine) -> None:
    with admin_engine.begin() as c:
        c.execute(text("UPDATE aprobari SET stare = 'anulat', decis_la = now() WHERE stare = 'in_asteptare'"))


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


def cerere(
    tenant: uuid.UUID, decident: Decident = Decident.OPERATOR, **kw: object
) -> tuple[uuid.UUID, productie.Aprobare]:
    lid = livrabil(tenant, **kw)  # type: ignore[arg-type]
    curenta = Stare.PLANIFICAT
    for s in (Stare.BRIEFAT, Stare.IN_SCRIERE, Stare.IN_VALIDARE, Stare.VALIDAT):
        muta(tenant, lid, curenta, s)
        curenta = s
    with sesiune_tenant(tenant) as db:
        return lid, aprobari.cere(db, lid, decident=decident)


def audit(admin: Engine, actiune: str, ap_id: uuid.UUID) -> list[dict[str, object]]:
    with admin.connect() as c:
        return [
            dict(r._mapping)
            for r in c.execute(
                text(
                    "SELECT utilizator_id, tenant_id, detalii FROM jurnal_audit WHERE actiune = :a AND obiect_id = :o"
                ),
                {"a": actiune, "o": str(ap_id)},
            )
        ]


def test_lista_arata_cererile_in_asteptare_cu_termen_si_versiune(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID
) -> None:
    _, ap = cerere(tenant, tip="video", canal="instagram")
    html = client.get("/aprobari").text
    assert "video · instagram" in html and "în așteptare" in html and "Așteaptă aprobare" in html
    assert f'action="/aprobari/{ap.id}/aproba"' in html and f'action="/aprobari/{ap.id}/respinge"' in html
    assert f'name="versiune" value="{ap.versiune}"' in html
    assert "Hook slab" in html, "motivele standard din 18.3"
    assert "UTC" in html, "termenul e afișat"
    assert 'aria-current="page"' in html and 'href="/aprobari" aria-current="page"' in html


def test_aprobarea_din_panou_cere_csrf_se_aplica_si_se_audita(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, admin_engine: Engine
) -> None:
    lid, ap = cerere(tenant)
    r = client.post(f"/aprobari/{ap.id}/aproba", data={"versiune": "1", "csrf_token": "gresit"})
    assert r.status_code == 403 and stare(tenant, lid) == Stare.ASTEAPTA_APROBARE
    r = client.post(f"/aprobari/{ap.id}/aproba", data={"versiune": "1"})
    assert r.status_code == 403, "fără jeton CSRF"
    r = client.post(
        f"/aprobari/{ap.id}/aproba",
        data={"versiune": "1", "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/aprobari?mesaj=aprobat"
    assert stare(tenant, lid) == Stare.APROBAT
    [a] = audit(admin_engine, "aprobare.aprobata", ap.id)
    assert a["utilizator_id"] == proprietar.id and a["tenant_id"] == tenant
    assert "Aprobarea a fost înregistrată" in client.get("/aprobari?mesaj=aprobat").text
    assert f"/aprobari/{ap.id}/aproba" not in client.get("/aprobari").text, (
        "decisă: dispare din „în așteptare”"
    )
    assert f'id="c-{ap.id}"' in client.get("/aprobari?stare=toate").text, "decisă, apare doar la „Toate”"


def test_o_a_doua_decizie_pe_aceeasi_cerere_este_refuzata_cu_mesaj(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID
) -> None:
    lid, ap = cerere(tenant)
    jeton = csrf(client)
    assert (
        client.post(
            f"/aprobari/{ap.id}/aproba", data={"versiune": "1", "csrf_token": jeton}, follow_redirects=False
        ).status_code
        == 303
    )
    r = client.post(
        f"/aprobari/{ap.id}/respinge",
        data={"versiune": "1", "motiv": "m-am răzgândit", "csrf_token": jeton},
    )
    assert r.status_code == 409 and "nu mai este în așteptare" in r.text
    assert stare(tenant, lid) == Stare.APROBAT


def test_respingerea_cere_motiv_si_il_scrie_in_audit(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, admin_engine: Engine
) -> None:
    lid, ap = cerere(tenant)
    jeton = csrf(client)
    r = client.post(f"/aprobari/{ap.id}/respinge", data={"versiune": "1", "motiv": " ", "csrf_token": jeton})
    assert r.status_code == 422 and "motiv" in r.text and stare(tenant, lid) == Stare.ASTEAPTA_APROBARE
    r = client.post(
        f"/aprobari/{ap.id}/respinge",
        data={
            "versiune": "1",
            "motiv_standard": "ton_nepotrivit",
            "motiv": "prea formal",
            "csrf_token": jeton,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303 and stare(tenant, lid) == Stare.RESPINS
    [a] = audit(admin_engine, "aprobare.respinsa", ap.id)
    assert a["detalii"]["motiv"] == "prea formal" and a["detalii"]["motiv_standard"] == "ton_nepotrivit"  # type: ignore[index]
    html = client.get("/aprobari?stare=toate").text
    assert "respins" in html and "Motiv: prea formal" in html


def test_decizia_pe_o_versiune_veche_este_refuzata(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID
) -> None:
    lid, ap = cerere(tenant)
    with sesiune_tenant(tenant) as db:  # între timp livrabilul s-a schimbat (versiunea 2, cerere nouă)
        productie.versiune_noua(db, lid, componenta="E1")
        noua = aprobari.cerere_activa(db, lid)
        assert noua is not None
    r = client.post(f"/aprobari/{noua.id}/aproba", data={"versiune": "1", "csrf_token": csrf(client)})
    assert r.status_code == 409 and "versiunea" in r.text and stare(tenant, lid) == Stare.ASTEAPTA_APROBARE
    r = client.post(f"/aprobari/{ap.id}/aproba", data={"versiune": "1", "csrf_token": csrf(client)})
    assert r.status_code == 409 and "anulat" in r.text


def test_cererea_expirata_nu_se_aproba_din_panou(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID
) -> None:
    lid = livrabil(tenant)
    for a, b in (
        (Stare.PLANIFICAT, Stare.BRIEFAT),
        (Stare.BRIEFAT, Stare.IN_SCRIERE),
        (Stare.IN_SCRIERE, Stare.IN_VALIDARE),
        (Stare.IN_VALIDARE, Stare.VALIDAT),
    ):
        muta(tenant, lid, a, b)
    with sesiune_tenant(tenant) as db:
        ap = aprobari.cere(db, lid, acum=dt.datetime.now(dt.UTC) - dt.timedelta(hours=49))
    r = client.post(f"/aprobari/{ap.id}/aproba", data={"versiune": "1", "csrf_token": csrf(client)})
    assert r.status_code == 409 and "a expirat, nu a fost aprobată" in r.text
    assert stare(tenant, lid) == Stare.EXPIRAT


def test_id_necunoscut_da_404_si_cererea_clientului_nu_are_butoane(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID
) -> None:
    jeton = csrf(client)
    for cale in (f"/aprobari/{uuid.uuid4()}/aproba", "/aprobari/nu-e-uuid/aproba"):
        assert client.post(cale, data={"versiune": "1", "csrf_token": jeton}).status_code == 404
    lid, ap = cerere(tenant, decident=Decident.CLIENT)
    html = client.get("/aprobari").text
    assert "Așteaptă decizia clientului" in html and f"/aprobari/{ap.id}/aproba" not in html
    r = client.post(f"/aprobari/{ap.id}/aproba", data={"versiune": "1", "csrf_token": jeton})
    assert r.status_code == 403, "agenția nu decide în locul clientului"
    assert stare(tenant, lid) == Stare.ASTEAPTA_APROBARE


def test_analistul_citeste_dar_nu_decide(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float], tenant: uuid.UUID
) -> None:
    lid, ap = cerere(tenant)
    analist = fabrica_conturi(Rol.ANALIST, cu_totp=True)
    autentifica(client, analist, ceas)
    assert client.get("/aprobari").status_code == 200
    r = client.post(f"/aprobari/{ap.id}/aproba", data={"versiune": "1", "csrf_token": csrf(client)})
    assert r.status_code == 403 and stare(tenant, lid) == Stare.ASTEAPTA_APROBARE


def test_operatorul_alocat_decide_pentru_clientul_lui(
    client: TestClient,
    fabrica_conturi: Fabrica,
    ceas: dict[str, float],
    tenant: uuid.UUID,
    fabrica_clienti: Callable[[], uuid.UUID],
    admin_engine: Engine,
) -> None:
    alt_client = fabrica_clienti()
    lid, ap = cerere(tenant)
    lid_altul, ap_altul = cerere(alt_client)
    operator = fabrica_conturi(Rol.OPERATOR, cu_totp=True)
    with admin_engine.begin() as c:
        c.execute(
            text("INSERT INTO alocari (id, utilizator_id, tenant_id) VALUES (:i, :u, :t)"),
            {"i": new_id(), "u": operator.id, "t": tenant},
        )
    autentifica(client, operator, ceas)
    r = client.post(
        "/conturi/client-activ",
        data={"tenant_id": str(tenant), "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code in (200, 303)
    html = client.get("/aprobari").text
    assert f"/aprobari/{ap.id}/aproba" in html and str(ap_altul.id) not in html, "doar clientul alocat"
    r = client.post(
        f"/aprobari/{ap.id}/aproba",
        data={"versiune": "1", "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303 and stare(tenant, lid) == Stare.APROBAT
    r = client.post(f"/aprobari/{ap_altul.id}/aproba", data={"versiune": "1", "csrf_token": csrf(client)})
    assert r.status_code == 404 and stare(alt_client, lid_altul) == Stare.ASTEAPTA_APROBARE


@pytest.mark.parametrize("rol", [Rol.CLIENT_TITULAR, Rol.CLIENT_APROBATOR, Rol.CLIENT_VIZITATOR])
def test_clientii_nu_au_acces_in_panou(client: TestClient, fabrica_conturi: Fabrica, rol: Rol) -> None:
    cont = fabrica_conturi(rol)
    login(client, cont.email, cont.parola)
    assert client.get("/aprobari").status_code == 403
    assert client.post(f"/aprobari/{uuid.uuid4()}/aproba", data={"versiune": "1"}).status_code == 403
