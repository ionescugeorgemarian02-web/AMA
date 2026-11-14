"""F1.5 — autentificarea cap-coadă prin HTTP: parolă + TOTP, sesiuni, CSRF, limitare, fără enumerare."""

import hashlib
import logging
import re
from collections.abc import Callable, Iterator, Sequence
from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.config import get_settings
from app.conturi import (
    DbSession,
    Permisiune,
    Rol,
    SesiuneCurenta,
    csrf_prelogin,
    csrf_protect,
    require_permission,
    require_role,
)
from app.main import create_app
from tests.integration.conftest import Cont, cod_totp, csrf_din, login, post_cod

pytestmark = pytest.mark.db

Fabrica = Callable[..., Cont]


def cookie_sesiune(client: TestClient) -> str | None:
    return client.cookies.get("ama_sesiune")


def autentifica(client: TestClient, cont: Cont, ceas: dict[str, float]) -> None:
    assert cont.secret
    r = login(client, cont.email, cont.parola)
    assert r.status_code == 303 and r.headers["location"] == "/conturi/2fa"
    ceas["t"] += 31  # alt pas de timp decât cel deja folosit (anti-reluare)
    r = post_cod(client, "/conturi/2fa", cod_totp(cont.secret, ceas["t"]))
    assert r.status_code == 303 and r.headers["location"] == "/conturi/eu", r.text


# ---- Gata când: login cap-coadă cu parolă + TOTP prin HTTP -------------------------------------------------


def test_login_complet_cu_parola_si_totp(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]
) -> None:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    assert client.get("/conturi/eu", follow_redirects=False).status_code == 303  # fără sesiune

    r = login(client, cont.email, cont.parola)
    assert (r.status_code, r.headers["location"]) == (303, "/conturi/2fa")
    # După parolă, dar înainte de al doilea factor, nu există acces.
    r = client.get("/conturi/eu", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/conturi/2fa")

    assert cont.secret
    r = post_cod(client, "/conturi/2fa", cod_totp(cont.secret, ceas["t"]))
    assert (r.status_code, r.headers["location"]) == (303, "/conturi/eu")
    pagina = client.get("/conturi/eu")
    assert pagina.status_code == 200
    assert cont.email in pagina.text and "Proprietar" in pagina.text


def test_inrolare_2fa_cap_coada_pentru_agentie(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]
) -> None:
    cont = fabrica_conturi(Rol.PROPRIETAR)  # rol de agenție fără 2FA: înrolarea este obligatorie
    r = login(client, cont.email, cont.parola)
    assert r.headers["location"] == "/conturi/2fa/inrolare"
    assert client.get("/conturi/eu", follow_redirects=False).headers["location"] == "/conturi/2fa/inrolare"

    pagina = client.get("/conturi/2fa/inrolare")
    secret = re.search(r'id="secret">([A-Z2-7]+)<', pagina.text)
    assert secret
    assert f"secret={secret.group(1)}" in pagina.text and "otpauth://totp/" in pagina.text

    r = client.post("/conturi/2fa/inrolare", data={"cod": "000000", "csrf_token": csrf_din(pagina.text)})
    assert r.status_code == 401
    r = client.post(
        "/conturi/2fa/inrolare",
        data={"cod": cod_totp(secret.group(1), ceas["t"]), "csrf_token": csrf_din(pagina.text)},
    )
    assert r.status_code == 200
    coduri = re.findall(r"<code>([A-Z0-9-]{19})</code>", r.text)
    assert len(coduri) == 10
    assert client.get("/conturi/eu").status_code == 200  # sesiunea rotită este completă

    # Secretul din bază este criptat, nu în clar.
    client.post("/conturi/iesire", headers={"x-csrf-token": csrf_din(client.get("/conturi/eu").text)})
    client.cookies.clear()
    ceas["t"] += 31
    autentifica(client, Cont(cont.id, cont.email, cont.parola, cont.rol, None, secret.group(1)), ceas)


def test_secretul_totp_si_codurile_nu_sunt_in_clar(
    client: TestClient, fabrica_conturi: Fabrica, admin_engine: Engine, ceas: dict[str, float]
) -> None:
    cont = fabrica_conturi(Rol.CLIENT_TITULAR)
    login(client, cont.email, cont.parola)
    pagina = client.get("/conturi/2fa/inrolare")
    secret = re.search(r'id="secret">([A-Z2-7]+)<', pagina.text)
    assert secret
    r = client.post(
        "/conturi/2fa/inrolare",
        data={"cod": cod_totp(secret.group(1), ceas["t"]), "csrf_token": csrf_din(pagina.text)},
    )
    coduri = re.findall(r"<code>([A-Z0-9-]{19})</code>", r.text)
    with admin_engine.connect() as c:
        enc = c.execute(
            text("SELECT totp_secret_enc FROM utilizatori WHERE id = :i"), {"i": cont.id}
        ).scalar_one()
        hashuri = [
            bytes(h)
            for (h,) in c.execute(
                text("SELECT cod_hash FROM coduri_recuperare WHERE utilizator_id = :i"), {"i": cont.id}
            )
        ]
    assert secret.group(1).encode() not in bytes(enc)
    assert len(hashuri) == 10
    for cod in coduri:
        assert cod.encode() not in b"".join(hashuri)
        assert cod.replace("-", "").encode() not in b"".join(hashuri)


# ---- Fără enumerare, limitare ------------------------------------------------------------------------------


def eroare(html: str) -> str:
    m = re.search(r'id="eroare">([^<]+)<', html)
    return m.group(1) if m else ""


def test_utilizator_necunoscut_si_parola_gresita_arata_la_fel(
    client: TestClient, fabrica_conturi: Fabrica
) -> None:
    cont = fabrica_conturi()
    gresita = login(client, cont.email, "parola-gresita-dar-lunga")
    necunoscut = login(client, "nimeni@exemplu.test", "parola-gresita-dar-lunga")
    assert gresita.status_code == necunoscut.status_code == 401
    assert eroare(gresita.text) == eroare(necunoscut.text) != ""
    assert re.sub(r'value="[^"]*"', "", gresita.text) == re.sub(r'value="[^"]*"', "", necunoscut.text)
    assert "ama_sesiune" not in client.cookies


def test_blocare_dupa_prea_multe_esecuri_inclusiv_cu_parola_buna(
    client: TestClient, fabrica_conturi: Fabrica
) -> None:
    cont = fabrica_conturi()
    prag = get_settings().login_max_failures_account
    for _ in range(prag):
        assert login(client, cont.email, "parola-gresita-dar-lunga").status_code == 401
    r = login(client, cont.email, cont.parola)
    assert r.status_code == 429 and "Prea multe" in r.text
    assert "ama_sesiune" not in client.cookies


def test_blocarea_se_aplica_si_conturilor_inexistente(client: TestClient) -> None:
    prag = get_settings().login_max_failures_account
    coduri = [
        login(client, "fantoma@exemplu.test", "parola-gresita-dar-lunga").status_code for _ in range(prag + 1)
    ]
    assert coduri == [401] * prag + [429]  # același comportament ca pentru un cont real


def test_blocare_pe_ip(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMA_LOGIN_MAX_FAILURES_IP", "3")
    get_settings.cache_clear()
    try:
        coduri = [
            login(client, f"cont{i}@exemplu.test", "parola-gresita-dar-lunga").status_code for i in range(5)
        ]
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
    assert coduri == [401, 401, 401, 429, 429]


def test_succesul_final_reseteaza_contorul_contului(client: TestClient, fabrica_conturi: Fabrica) -> None:
    cont = fabrica_conturi()
    for _ in range(get_settings().login_max_failures_account - 1):
        login(client, cont.email, "parola-gresita-dar-lunga")
    assert login(client, cont.email, cont.parola).status_code == 303
    client.cookies.clear()
    for _ in range(get_settings().login_max_failures_account - 1):
        assert login(client, cont.email, "parola-gresita-dar-lunga").status_code == 401


def test_greseli_la_al_doilea_factor_se_numara_si_blocheaza(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]
) -> None:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    login(client, cont.email, cont.parola)
    prag = get_settings().login_max_failures_account
    coduri = [post_cod(client, "/conturi/2fa", "000000").status_code for _ in range(prag + 1)]
    assert coduri[-1] == 429
    assert cod_totp(cont.secret or "", ceas["t"])  # chiar și un cod bun e refuzat cât timp contul e blocat
    assert post_cod(client, "/conturi/2fa", cod_totp(cont.secret or "", ceas["t"])).status_code == 429


# ---- Reluare cod, recuperare -----------------------------------------------------------------------------


def test_codul_totp_nu_poate_fi_reluat(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]
) -> None:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    cod = cod_totp(cont.secret or "", ceas["t"])
    login(client, cont.email, cont.parola)
    assert post_cod(client, "/conturi/2fa", cod).status_code == 303
    client.cookies.clear()
    login(client, cont.email, cont.parola)
    r = post_cod(client, "/conturi/2fa", cod)  # același cod, același pas de timp
    assert r.status_code == 401
    ceas["t"] += 30
    assert post_cod(client, "/conturi/2fa", cod_totp(cont.secret or "", ceas["t"])).status_code == 303


def test_codul_de_recuperare_se_foloseste_o_singura_data(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]
) -> None:
    cont = fabrica_conturi(Rol.CLIENT_TITULAR)
    login(client, cont.email, cont.parola)
    pagina = client.get("/conturi/2fa/inrolare")
    secret = re.search(r'id="secret">([A-Z2-7]+)<', pagina.text)
    assert secret
    r = client.post(
        "/conturi/2fa/inrolare",
        data={"cod": cod_totp(secret.group(1), ceas["t"]), "csrf_token": csrf_din(pagina.text)},
    )
    cod = re.findall(r"<code>([A-Z0-9-]{19})</code>", r.text)[0]
    client.cookies.clear()
    login(client, cont.email, cont.parola)
    assert (
        post_cod(client, "/conturi/2fa", cod.lower()).status_code == 303
    )  # acceptat (fără diferență de majuscule)
    client.cookies.clear()
    login(client, cont.email, cont.parola)
    assert post_cod(client, "/conturi/2fa", cod).status_code == 401  # a doua oară: refuzat


# ---- Sesiuni -----------------------------------------------------------------------------------------------


def test_cookie_si_jetonul_in_baza(
    client: TestClient, fabrica_conturi: Fabrica, admin_engine: Engine
) -> None:
    cont = fabrica_conturi()
    r = login(client, cont.email, cont.parola)
    antet = next(h for h in r.headers.get_list("set-cookie") if h.startswith("ama_sesiune=")).lower()
    assert "httponly" in antet and "samesite=lax" in antet and "secure" not in antet  # test: fără Secure
    jeton = cookie_sesiune(client)
    assert jeton and len(jeton) >= 43  # 256 de biți în base64url
    with admin_engine.connect() as c:
        hashuri = [
            bytes(h)
            for (h,) in c.execute(
                text("SELECT token_hash FROM sesiuni WHERE utilizator_id = :i"), {"i": cont.id}
            )
        ]
    assert hashlib.sha256(jeton.encode()).digest() in hashuri
    assert jeton.encode() not in b"".join(hashuri)


def test_cookie_secure_si_prefix_host_in_afara_dev(
    client: TestClient, fabrica_conturi: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    cont = fabrica_conturi()
    monkeypatch.setenv("AMA_ENV", "staging")
    monkeypatch.setenv("AMA_SECRET_KEY", "s" * 40)
    get_settings.cache_clear()
    try:
        with TestClient(create_app(), base_url="https://testserver", client=("203.0.113.9", 1)) as https:
            r = login(https, cont.email, cont.parola)
            antete = [h.lower() for h in r.headers.get_list("set-cookie")]
            sesiune = [h for h in antete if h.startswith("__host-ama_sesiune=")]
            assert sesiune and all(x in sesiune[0] for x in ("httponly", "secure", "samesite=lax", "path=/"))
            assert "domain" not in sesiune[0]
            assert r.headers["strict-transport-security"].startswith("max-age=")
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_sesiunea_se_roteste_la_parola_si_la_al_doilea_factor(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]
) -> None:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    client.cookies.set(
        "ama_sesiune", "jeton-fixat-de-atacator", domain="testserver.local"
    )  # fixare de sesiune
    login(client, cont.email, cont.parola)
    dupa_parola = cookie_sesiune(client)
    assert dupa_parola and dupa_parola != "jeton-fixat-de-atacator"
    post_cod(client, "/conturi/2fa", cod_totp(cont.secret or "", ceas["t"]))
    dupa_2fa = cookie_sesiune(client)
    assert dupa_2fa and dupa_2fa != dupa_parola
    # Jetonul din etapa „parolă” nu mai are nicio valoare.
    vechi = TestClient(client.app, client=("203.0.113.7", 1), cookies={"ama_sesiune": dupa_parola})
    assert vechi.get("/conturi/eu", follow_redirects=False).status_code == 303
    assert client.get("/conturi/eu").status_code == 200


def test_ieșirea_revoca_sesiunea(client: TestClient, fabrica_conturi: Fabrica) -> None:
    cont = fabrica_conturi()
    login(client, cont.email, cont.parola)
    jeton = cookie_sesiune(client)
    pagina = client.get("/conturi/eu")
    r = client.post("/conturi/iesire", data={"csrf_token": csrf_din(pagina.text)}, follow_redirects=False)
    assert r.status_code == 303
    copie = TestClient(client.app, client=("203.0.113.7", 1), cookies={"ama_sesiune": jeton or ""})
    assert copie.get("/conturi/eu", follow_redirects=False).status_code == 303  # jetonul furat nu mai merge


@pytest.mark.parametrize(
    ("coloana", "valoare"),
    [("ultima_activitate", "now() - interval '2 hours'"), ("expira_absolut", "now() - interval '1 second'")],
)
def test_sesiunea_expira(
    client: TestClient, fabrica_conturi: Fabrica, admin_engine: Engine, coloana: str, valoare: str
) -> None:
    cont = fabrica_conturi()
    login(client, cont.email, cont.parola)
    assert client.get("/conturi/eu").status_code == 200
    with admin_engine.begin() as c:
        c.execute(text(f"UPDATE sesiuni SET {coloana} = {valoare} WHERE utilizator_id = :i"), {"i": cont.id})
    assert client.get("/conturi/eu", follow_redirects=False).status_code == 303


def test_utilizator_blocat_sau_sters_pierde_sesiunea(
    client: TestClient, fabrica_conturi: Fabrica, admin_engine: Engine
) -> None:
    cont = fabrica_conturi()
    login(client, cont.email, cont.parola)
    with admin_engine.begin() as c:
        c.execute(text("UPDATE utilizatori SET stare = 'blocat' WHERE id = :i"), {"i": cont.id})
    assert client.get("/conturi/eu", follow_redirects=False).status_code == 303
    assert login(client, cont.email, cont.parola).status_code == 401


# ---- CSRF ------------------------------------------------------------------------------------------------


def test_post_fara_jeton_csrf_este_respins(client: TestClient, fabrica_conturi: Fabrica) -> None:
    cont = fabrica_conturi()
    # Autentificarea cere jetonul dublu-trimis.
    assert client.post("/conturi/login", data={"email": cont.email, "parola": cont.parola}).status_code == 403
    client.get("/conturi/login")
    r = client.post(
        "/conturi/login", data={"email": cont.email, "parola": cont.parola, "csrf_token": "altceva"}
    )
    assert r.status_code == 403
    login(client, cont.email, cont.parola)
    assert client.post("/conturi/iesire").status_code == 403
    assert client.post("/conturi/iesire", data={"csrf_token": "gresit"}).status_code == 403
    assert client.get("/conturi/eu").status_code == 200  # sesiunea a rămas


def test_csrf_prin_antet_pentru_htmx(client: TestClient, fabrica_conturi: Fabrica) -> None:
    cont = fabrica_conturi()
    login(client, cont.email, cont.parola)
    jeton = csrf_din(client.get("/conturi/eu").text)
    assert "X-CSRF-Token" in client.get("/conturi/eu").text  # hx-headers în base.html
    r = client.post("/conturi/iesire", headers={"X-CSRF-Token": jeton}, follow_redirects=False)
    assert r.status_code == 303


def test_jetonul_csrf_este_legat_de_sesiune(client: TestClient, fabrica_conturi: Fabrica) -> None:
    a, b = fabrica_conturi(), fabrica_conturi()
    login(client, a.email, a.parola)
    jeton_a = csrf_din(client.get("/conturi/eu").text)
    client.cookies.clear()
    login(client, b.email, b.parola)
    assert client.post("/conturi/iesire", data={"csrf_token": jeton_a}).status_code == 403


def _apeleaza(dependant: object) -> set[object]:
    gasite: set[object] = set()
    for d in getattr(dependant, "dependencies", []):
        gasite.add(d.call)
        gasite |= _apeleaza(d)
    return gasite


def _rute_api(rute: Sequence[object]) -> Iterator[Any]:
    """Parcurge rutele, inclusiv pe cele din routere incluse (FastAPI le păstrează în `original_router`)."""
    from fastapi.routing import APIRoute

    for ruta in rute:
        if isinstance(ruta, APIRoute):
            yield ruta
        elif hasattr(ruta, "original_router"):
            yield from _rute_api(ruta.original_router.routes)


def test_toate_rutele_care_schimba_starea_au_garda_csrf() -> None:
    garzi = {csrf_protect, csrf_prelogin}
    verificate = [r for r in _rute_api(create_app().routes) if r.methods & {"POST", "PUT", "PATCH", "DELETE"}]
    # Singurele excepții, explicite și înguste: apeluri de la mașină la mașină, fără browser și fără cookie, deci
    # fără ce să falsifice. Se apără prin alt mecanism, verificat în testele lor (jeton comparat în timp
    # constant; antet-secret + listă de conversații): `tests/integration/test_livrare_panou.py` și `test_telegram.py`.
    # Webhook-ul procesatorului de plăți (F7.6) se apără prin semnătura HMAC a corpului și vechimea evenimentului:
    # `tests/integration/test_facturare.py`.
    fara_csrf_justificat = {"/intern/livrare/rezultat", "/telegram/webhook", "/facturare/webhook"}
    nepazite = [
        r.path
        for r in verificate
        if not garzi & _apeleaza(r.dependant) and r.path not in fara_csrf_justificat
    ]
    assert fara_csrf_justificat <= {r.path for r in verificate}, "lista de excepții nu mai corespunde rutelor"
    assert len(verificate) >= 5, "nu am găsit rutele (testul și-ar pierde sensul)"
    assert not nepazite, f"rute fără protecție CSRF: {nepazite}"


# ---- Dependențe: current_user, require_role, db_session ----------------------------------------------------


@pytest.fixture
def aplicatie_cu_rute() -> Iterator[TestClient]:
    app = create_app()
    r = APIRouter()

    @r.get("/proba/proprietar")
    def doar_proprietar(
        u: Annotated[SesiuneCurenta, Depends(require_role(Rol.PROPRIETAR))],
    ) -> dict[str, str]:
        return {"rol": u.rol.value}

    @r.get("/proba/livrabile")
    def livrabile(
        u: Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.LIVRABIL_APROBA))],
    ) -> dict[str, str]:
        return {"rol": u.rol.value}

    @r.get("/proba/clienti")
    def clienti(db: DbSession) -> list[str]:
        return sorted(str(x) for x in db.execute(text("SELECT id FROM clienti")).scalars())

    app.include_router(r)
    with TestClient(app, client=("203.0.113.8", 1)) as c:
        yield c


def test_require_role_si_permisiune(aplicatie_cu_rute: TestClient, fabrica_conturi: Fabrica) -> None:
    c = aplicatie_cu_rute
    assert c.get("/proba/proprietar", follow_redirects=False).status_code == 303  # neautentificat
    vizitator = fabrica_conturi(Rol.CLIENT_VIZITATOR)
    login(c, vizitator.email, vizitator.parola)
    assert c.get("/proba/proprietar").status_code == 403
    assert c.get("/proba/livrabile").status_code == 403
    c.cookies.clear()
    aprobator = fabrica_conturi(Rol.CLIENT_APROBATOR)
    login(c, aprobator.email, aprobator.parola)
    assert c.get("/proba/livrabile").status_code == 200
    assert c.get("/proba/proprietar").status_code == 403


def test_db_session_aplica_clientul_din_sesiune(
    aplicatie_cu_rute: TestClient, fabrica_conturi: Fabrica
) -> None:
    c = aplicatie_cu_rute
    a, b = fabrica_conturi(Rol.CLIENT_TITULAR), fabrica_conturi(Rol.CLIENT_TITULAR)
    login(c, a.email, a.parola)
    assert c.get("/proba/clienti").json() == [str(a.tenant_id)]  # doar clientul propriu
    c.cookies.clear()
    login(c, b.email, b.parola)
    assert c.get("/proba/clienti").json() == [str(b.tenant_id)]


def test_operatorul_vede_doar_clientul_activ_alocat(
    aplicatie_cu_rute: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]
) -> None:
    from app.conturi.servicii import Actor, aloca_operator
    from app.db import sesiune_agentie

    c = aplicatie_cu_rute
    a, b = fabrica_conturi(Rol.CLIENT_TITULAR), fabrica_conturi(Rol.CLIENT_TITULAR)
    op = fabrica_conturi(Rol.OPERATOR, cu_totp=True)
    with sesiune_agentie() as db:
        aloca_operator(db, op.id, a.tenant_id, actor=Actor.cli())  # type: ignore[arg-type]
    autentifica(c, op, ceas)
    assert c.get("/proba/clienti").json() == [str(a.tenant_id)]  # clienții alocați, fără client activ ales
    csrf = csrf_din(c.get("/conturi/eu").text)
    # Alocat: poate alege. Nealocat: refuzat.
    assert (
        c.post("/conturi/client-activ", data={"tenant_id": str(b.tenant_id), "csrf_token": csrf}).status_code
        == 403
    )
    r = c.post(
        "/conturi/client-activ",
        data={"tenant_id": str(a.tenant_id), "csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "Client:" in c.get("/conturi/eu").text
    assert c.get("/proba/clienti").json() == [str(a.tenant_id)]


# ---- Antete și jurnale ----------------------------------------------------------------------------------------


def test_antete_de_securitate(client: TestClient) -> None:
    r = client.get("/conturi/login")
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"]
    assert r.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in r.headers  # dev/test
    # nimic inline: scripturile sunt doar fișiere externe (CSP `script-src 'self'`)
    assert not re.search(r"<script(?![^>]*\bsrc=)", r.text) and "style=" not in r.text


def test_nicio_parola_cod_sau_jeton_in_jurnale(
    client: TestClient, fabrica_conturi: Fabrica, caplog: pytest.LogCaptureFixture, ceas: dict[str, float]
) -> None:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    caplog.set_level(logging.DEBUG)
    login(client, cont.email, "parola-gresita-dar-lunga")
    login(client, cont.email, cont.parola)
    cod = cod_totp(cont.secret or "", ceas["t"])
    post_cod(client, "/conturi/2fa", cod)
    jeton = cookie_sesiune(client) or ""
    ieșire = caplog.text + "".join(str(r.__dict__) for r in caplog.records)
    for secret in (cont.parola, "parola-gresita-dar-lunga", cod, jeton, cont.secret or "?"):
        assert secret not in ieșire
