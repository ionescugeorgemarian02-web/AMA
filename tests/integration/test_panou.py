"""F1.7 — coaja panoului: pagini, acces, butoane de oprire, conducta de notificări push."""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.conturi import Rol
from app.operare import notificari
from app.operare.notificari import Nivel
from tests.integration.conftest import Cont
from tests.integration.utile_panou import (
    CHEIE_PRIVATA,
    CHEIE_PUBLICA,
    BotFals,
    TrimitatorFals,
    autentifica,
    csrf,
)

pytestmark = pytest.mark.db

Fabrica = Callable[..., Cont]
PAGINI = ["/", "/aprobari", "/productie", "/alerte", "/meniu", "/meniu/notificari"]
ENDPOINT_A = "https://push.exemplu.test/abonament/" + "a" * 40
ENDPOINT_B = "https://push.exemplu.test/abonament/" + "b" * 40
CHEI = {"p256dh": "P" * 40, "auth": "A" * 20}


def randuri(admin: Engine, sql: str, **p: object) -> list[dict[str, object]]:
    with admin.connect() as c:
        return [dict(r._mapping) for r in c.execute(text(sql), p)]


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


# ---- pagini și acces ------------------------------------------------------------------------------------


@pytest.mark.parametrize("cale", PAGINI)
def test_paginile_se_afiseaza_pentru_proprietarul_cu_2fa(
    client: TestClient, proprietar: Cont, cale: str
) -> None:
    r = client.get(cale)
    assert r.status_code == 200, cale
    assert r.headers["cache-control"] == "no-store"  # paginile autentificate nu se țin în cache
    assert '<html lang="ro">' in r.text and 'rel="manifest"' in r.text
    assert 'name="csrf-token"' in r.text and "apple-mobile-web-app-capable" in r.text


@pytest.mark.parametrize("cale", PAGINI)
def test_anonimul_este_trimis_la_login(client: TestClient, cale: str) -> None:
    r = client.get(cale, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/conturi/login"


@pytest.mark.parametrize("cale", PAGINI)
def test_fara_al_doilea_factor_nu_exista_acces(
    client: TestClient, fabrica_conturi: Fabrica, cale: str
) -> None:
    from tests.integration.conftest import login

    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    login(client, cont.email, cont.parola)
    r = client.get(cale, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/conturi/2fa"


@pytest.mark.parametrize("cale", PAGINI)
def test_rolurile_de_client_primesc_403(client: TestClient, fabrica_conturi: Fabrica, cale: str) -> None:
    from tests.integration.conftest import login

    cont = fabrica_conturi(Rol.CLIENT_TITULAR)
    assert login(client, cont.email, cont.parola).status_code == 303
    assert client.get(cale, follow_redirects=False).status_code == 403


def test_bara_de_jos_are_cele_cinci_file_in_ordine_si_marcheaza_pagina_curenta(
    client: TestClient, proprietar: Cont
) -> None:
    html = client.get("/aprobari").text
    etichete = ["Acasă", "Aprobări", "Producție", "Alerte", "Meniu"]
    pozitii = [html.index(f"<span>{e}</span>") for e in etichete]
    assert pozitii == sorted(pozitii)
    assert html.count('aria-current="page"') == 1 and 'href="/aprobari" aria-current="page"' in html


def test_productie_este_stare_goala_onesta(client: TestClient, proprietar: Cont) -> None:
    html = client.get("/productie").text
    assert "Încă nimic aici" in html and "faza F2" in html


def test_aprobari_fara_cereri_este_stare_goala_onesta(client: TestClient, proprietar: Cont) -> None:
    # Ecranul Aprobări are conținut din F2.8 (lista cererilor); fără cereri arată o stare goală onestă.
    html = client.get("/aprobari").text
    assert "Nicio cerere în așteptare" in html and "Fără decizie la timp, un livrabil nu se publică" in html


def test_meniu_trimite_la_operare_cont_notificari_si_iesire(client: TestClient, proprietar: Cont) -> None:
    html = client.get("/meniu").text
    for legatura in (
        "/operare",
        "/meniu/notificari",
        "/conturi/eu",
        "/conturi/2fa/inrolare",
        "/conturi/iesire",
    ):
        assert legatura in html, legatura


def test_operatorul_vede_coaja_dar_nu_operare_si_nu_butoanele_de_oprire(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]
) -> None:
    op = fabrica_conturi(Rol.OPERATOR, cu_totp=True)
    autentifica(client, op, ceas)
    acasa = client.get("/")
    assert acasa.status_code == 200 and "Doar proprietarul poate folosi butoanele de oprire" in acasa.text
    assert 'action="/opriri/opreste"' not in acasa.text
    assert "/operare" not in client.get("/meniu").text.replace("/meniu/notificari", "")
    assert client.get("/operare").status_code == 403


def test_acasa_arata_starea_si_spune_ca_steagurile_nu_sunt_citite_inca(
    client: TestClient, proprietar: Cont
) -> None:
    html = client.get("/").text
    for text_ in (
        "Starea sistemului",
        "Baza de date",
        "Backup",
        "Butoane de oprire",
        "publicare",
        "doar se înregistrează",
    ):
        assert text_.lower() in html.lower(), text_
    assert 'hx-get="/fragment/stare"' in html
    frag = client.get("/fragment/stare")
    assert frag.status_code == 200 and "<html" not in frag.text and "Starea sistemului" in frag.text


# ---- butoanele de oprire din panou ---------------------------------------------------------------------


def audit_oprire(admin: Engine, actiune: str) -> list[dict[str, object]]:
    return randuri(
        admin,
        "SELECT * FROM jurnal_audit WHERE actiune = :a AND detalii->>'canal' = 'panou' ORDER BY id",
        a=actiune,
    )


def test_oprirea_din_panou_este_imediata_auditata_si_vizibila(
    client: TestClient, proprietar: Cont, admin_engine: Engine
) -> None:
    r = client.post(
        "/opriri/opreste",
        data={"tip": "publicare", "motiv": "test", "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    rand = randuri(admin_engine, "SELECT * FROM opriri WHERE tip = 'publicare'")[0]
    assert rand["activ"] is True and rand["canal"] == "panou" and rand["schimbat_de"] == proprietar.id
    a = audit_oprire(admin_engine, "oprire.oprit")[-1]
    assert a["utilizator_id"] == proprietar.id and a["detalii"]["motiv"] == "test"  # type: ignore[index]
    assert "oprit" in client.get("/").text


def test_repornirea_cere_confirmare_si_nu_porneste_fara_ea(
    client: TestClient, proprietar: Cont, admin_engine: Engine
) -> None:
    jeton = csrf(client)
    client.post("/opriri/opreste", data={"tip": "reclame", "csrf_token": jeton})
    pagina = client.get("/opriri/confirma-pornire?tip=reclame")
    assert (
        pagina.status_code == 200
        and "Da, repornește" in pagina.text
        and 'name="confirmare" value="da"' in pagina.text
    )
    # fără câmpul de confirmare: respins
    r = client.post("/opriri/porneste", data={"tip": "reclame", "csrf_token": jeton})
    assert r.status_code == 422
    assert randuri(admin_engine, "SELECT activ FROM opriri WHERE tip = 'reclame'")[0]["activ"] is True
    r = client.post(
        "/opriri/porneste",
        data={"tip": "reclame", "confirmare": "da", "csrf_token": jeton},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert randuri(admin_engine, "SELECT activ FROM opriri WHERE tip = 'reclame'")[0]["activ"] is False
    assert audit_oprire(admin_engine, "oprire.repornit")


def test_oprirea_pe_client_din_panou(
    client: TestClient, proprietar: Cont, fabrica_conturi: Fabrica, admin_engine: Engine
) -> None:
    titular = fabrica_conturi(Rol.CLIENT_TITULAR)
    assert titular.tenant_id
    html = client.get("/").text
    assert str(titular.tenant_id) in html  # clientul apare în listă
    r = client.post(
        "/opriri/opreste",
        data={"tip": "client", "tenant_id": str(titular.tenant_id), "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    rand = randuri(admin_engine, "SELECT * FROM opriri WHERE tip = 'client'")[0]
    assert rand["tenant_id"] == titular.tenant_id and rand["activ"] is True
    assert audit_oprire(admin_engine, "oprire.oprit")[-1]["tenant_id"] == titular.tenant_id


@pytest.mark.parametrize(
    "date",
    [
        {"tip": "nu_exista"},
        {"tip": "client"},
        {"tip": "client", "tenant_id": "nu-e-uuid"},
        {"tip": "client", "tenant_id": str(uuid.uuid4())},
    ],
)
def test_oprire_cu_date_nevalide_este_respinsa(
    client: TestClient, proprietar: Cont, date: dict[str, str]
) -> None:
    r = client.post("/opriri/opreste", data={**date, "csrf_token": csrf(client)})
    assert r.status_code == 422


def test_oprirea_cere_jeton_csrf_si_permisiune(
    client: TestClient,
    fabrica_conturi: Fabrica,
    ceas: dict[str, float],
    proprietar: Cont,
    admin_engine: Engine,
) -> None:
    assert (
        client.post("/opriri/opreste", data={"tip": "publicare", "csrf_token": "gresit"}).status_code == 403
    )
    assert randuri(admin_engine, "SELECT * FROM opriri") == []
    client.post("/conturi/iesire", data={"csrf_token": csrf(client)})
    op = fabrica_conturi(Rol.OPERATOR, cu_totp=True)
    autentifica(client, op, ceas)
    r = client.post("/opriri/opreste", data={"tip": "publicare", "csrf_token": csrf(client)})
    assert r.status_code == 403
    assert randuri(admin_engine, "SELECT * FROM opriri") == []


# ---- notificări push ---------------------------------------------------------------------------------------


def aboneaza(client: TestClient, endpoint: str = ENDPOINT_A):  # type: ignore[no-untyped-def]
    return client.post(
        "/notificari/aboneaza",
        json={"endpoint": endpoint, "keys": CHEI},
        headers={"X-CSRF-Token": csrf(client)},
    )


def test_fara_chei_vapid_push_este_dezactivat_si_pagina_o_spune(client: TestClient, proprietar: Cont) -> None:
    html = client.get("/meniu/notificari").text
    assert "dezactivate" in html and "AMA_VAPID_PUBLIC_KEY" in html and 'data-vapid=""' in html
    assert aboneaza(client).status_code == 503
    assert client.post("/notificari/test", headers={"X-CSRF-Token": csrf(client)}).status_code == 503


def test_cu_chei_vapid_pagina_primeste_cheia_publica_dar_nu_pe_cea_privata(
    client: TestClient, proprietar: Cont, config: Callable[..., None]
) -> None:
    config(vapid_public_key=CHEIE_PUBLICA, vapid_private_key=CHEIE_PRIVATA)
    html = client.get("/meniu/notificari").text
    assert f'data-vapid="{CHEIE_PUBLICA}"' in html and CHEIE_PRIVATA not in html
    assert "dezactivate" not in html


def test_abonare_apoi_notificare_de_test_apeleaza_trimitatorul_cu_sarcina_corecta(
    client: TestClient, proprietar: Cont, push: TrimitatorFals, admin_engine: Engine
) -> None:
    assert aboneaza(client).json() == {"ok": True}
    assert aboneaza(client).json() == {"ok": True}  # repetarea nu dublează
    rand = randuri(admin_engine, "SELECT * FROM abonamente_push")
    assert len(rand) == 1 and rand[0]["utilizator_id"] == proprietar.id and rand[0]["endpoint"] == ENDPOINT_A

    r = client.post("/notificari/test", headers={"X-CSRF-Token": csrf(client)})
    assert r.status_code == 200 and r.json() == {"trimise": 1, "sterse": 0, "esuate": 0}
    assert len(push.apeluri) == 1
    dest, payload = push.apeluri[0]
    assert (dest.endpoint, dest.p256dh, dest.auth) == (ENDPOINT_A, CHEI["p256dh"], CHEI["auth"])
    assert payload == {
        "titlu": "Notificare de test",
        "text": "Dacă vezi acest mesaj, notificările funcționează.",
        "url": "/meniu/notificari",
        "nivel": "informativ",
    }
    assert (
        randuri(admin_engine, "SELECT ultima_trimitere FROM abonamente_push")[0]["ultima_trimitere"]
        is not None
    )
    actiuni = {
        r["actiune"]
        for r in randuri(
            admin_engine, "SELECT actiune FROM jurnal_audit WHERE utilizator_id = :u", u=proprietar.id
        )
    }
    assert {"notificari.abonare", "notificari.test"} <= actiuni


def test_abonament_mort_410_este_sters(
    client: TestClient, proprietar: Cont, push: TrimitatorFals, admin_engine: Engine
) -> None:
    aboneaza(client, ENDPOINT_A)
    aboneaza(client, ENDPOINT_B)
    push.moarte.add(ENDPOINT_A)
    r = client.post("/notificari/test", headers={"X-CSRF-Token": csrf(client)})
    assert r.json() == {"trimise": 1, "sterse": 1, "esuate": 0}
    assert [x["endpoint"] for x in randuri(admin_engine, "SELECT endpoint FROM abonamente_push")] == [
        ENDPOINT_B
    ]


def test_esec_de_retea_nu_sterge_abonamentul_si_este_numarat(
    client: TestClient, proprietar: Cont, push: TrimitatorFals, admin_engine: Engine
) -> None:
    aboneaza(client)
    push.cade = True
    r = client.post("/notificari/test", headers={"X-CSRF-Token": csrf(client)})
    assert r.json() == {"trimise": 0, "sterse": 0, "esuate": 1}
    assert len(randuri(admin_engine, "SELECT 1 FROM abonamente_push")) == 1


def test_testul_fara_abonamente_da_409_si_dezabonarea_sterge(
    client: TestClient, proprietar: Cont, push: TrimitatorFals, admin_engine: Engine
) -> None:
    assert client.post("/notificari/test", headers={"X-CSRF-Token": csrf(client)}).status_code == 409
    aboneaza(client)
    r = client.post(
        "/notificari/dezaboneaza", json={"endpoint": ENDPOINT_A}, headers={"X-CSRF-Token": csrf(client)}
    )
    assert r.status_code == 200 and randuri(admin_engine, "SELECT 1 FROM abonamente_push") == []


def test_rutele_push_cer_csrf_si_endpoint_https(
    client: TestClient, proprietar: Cont, push: TrimitatorFals
) -> None:
    assert client.post("/notificari/aboneaza", json={"endpoint": ENDPOINT_A, "keys": CHEI}).status_code == 403
    r = client.post(
        "/notificari/aboneaza",
        json={"endpoint": "http://nesigur.test/x" + "y" * 20, "keys": CHEI},
        headers={"X-CSRF-Token": csrf(client)},
    )
    assert r.status_code == 422


def test_un_endpoint_al_altui_cont_da_409_nu_il_fura(
    client: TestClient,
    proprietar: Cont,
    push: TrimitatorFals,
    fabrica_conturi: Fabrica,
    ceas: dict[str, float],
    admin_engine: Engine,
) -> None:
    aboneaza(client)
    client.post("/conturi/iesire", data={"csrf_token": csrf(client)})
    op = fabrica_conturi(Rol.OPERATOR, cu_totp=True)
    autentifica(client, op, ceas)
    assert aboneaza(client).status_code == 409
    assert (
        randuri(admin_engine, "SELECT utilizator_id FROM abonamente_push")[0]["utilizator_id"]
        == proprietar.id
    )


# ---- rutarea notificărilor către canale -----------------------------------------------------------------


def test_notifica_critic_trimite_si_pe_push_si_pe_telegram_iar_informativ_pe_niciunul(
    client: TestClient, proprietar: Cont, push: TrimitatorFals, bot_fals: BotFals
) -> None:
    aboneaza(client)
    r = notificari.notifica(Nivel.CRITIC, "Sistem oprit", "Baza nu răspunde")
    assert r == {notificari.Canal.PUSH: True, notificari.Canal.TELEGRAM: True}
    assert push.apeluri[-1][1]["nivel"] == "critic"
    assert bot_fals.mesaje() == ["[CRITIC] Sistem oprit\nBaza nu răspunde"]

    n_push = len(push.apeluri)
    notificari.notifica(Nivel.IMPORTANT, "Aprobare expiră", "În 2 ore")
    assert len(push.apeluri) == n_push + 1 and len(bot_fals.mesaje()) == 1  # important: doar push

    assert notificari.notifica(Nivel.INFORMATIV, "Raport", "Gata") == {}
    assert len(push.apeluri) == n_push + 1 and len(bot_fals.mesaje()) == 1


def test_notifica_nu_strica_apelantul_cand_canalele_cad(
    client: TestClient, proprietar: Cont, push: TrimitatorFals, bot_fals: BotFals
) -> None:
    aboneaza(client)
    push.cade = True
    bot_fals.status, bot_fals.corp = 502, {"ok": False, "error_code": 502, "description": "Bad Gateway"}
    r = notificari.notifica(Nivel.CRITIC, "Sistem oprit", "Baza nu răspunde")
    assert r == {notificari.Canal.PUSH: False, notificari.Canal.TELEGRAM: False}


def test_notifica_fara_nimic_configurat_nu_arunca() -> None:
    r = notificari.notifica(Nivel.CRITIC, "t", "x")
    assert r == {notificari.Canal.PUSH: False, notificari.Canal.TELEGRAM: False}
