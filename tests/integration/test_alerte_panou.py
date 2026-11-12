"""F2.7 — ecranul Alerte: listă pe cauze, detaliu, „reia” și „închide”, cu CSRF, permisiuni și audit."""

import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.conturi import Rol
from app.db import sesiune_agentie
from app.operare import coada_erori, motor
from app.operare.tabele import IntrareEroare
from app.operare.watchdog import Watchdog
from tests.integration import fluxuri_watchdog as flux
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf

pytestmark = pytest.mark.db
Fabrica = Callable[..., Cont]
Pornire = Callable[..., None]


@pytest.fixture(autouse=True)
def _curat(porneste_executor: Pornire, admin_engine: Engine) -> Iterator[None]:
    with admin_engine.begin() as c:
        c.execute(text("TRUNCATE coada_erori, worker_semnale, worker_evenimente"))
    flux.reseteaza()
    yield
    flux.elibereaza()
    flux.reseteaza()


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


def watchdog() -> Watchdog:
    return Watchdog(
        "worker-local",
        bataie_sec=1,
        scanare_sec=1,
        timeout_sec=60,
        prag_reporniri=3,
        fereastra_min=60,
        prag_crestere=5,
    )


def client_nou(admin: Engine) -> str:
    cid = uuid.uuid4()
    with admin.begin() as c:
        c.execute(text("INSERT INTO clienti (id, nume) VALUES (:i, 'Firma Panou')"), {"i": cid})
    return str(cid)


def job_esuat(admin: Engine, fluxul: Callable[..., object], nume: str) -> IntrareEroare:
    job = motor.trimite(fluxul, client_nou(admin), nume, cheie=f"ap-{nume}")
    assert motor.asteapta_flux(job, timeout_sec=20).stare is motor.StareJob.ESUAT
    watchdog().scaneaza()
    return intrare(job)


def intrare(workflow_id: str) -> IntrareEroare:
    with sesiune_agentie() as db:
        i = db.query(IntrareEroare).filter_by(workflow_id=workflow_id).one()
        db.expunge(i)
        return i


def audit(admin: Engine, actiune: str, obiect_id: object = None) -> list[dict[str, object]]:
    with admin.connect() as c:
        return [
            dict(r._mapping)
            for r in c.execute(
                text(
                    "SELECT actiune, obiect_id, utilizator_id, tenant_id, detalii FROM jurnal_audit "
                    "WHERE actiune = :a AND (CAST(:o AS text) IS NULL OR obiect_id = :o)"
                ),
                {"a": actiune, "o": None if obiect_id is None else str(obiect_id)},
            )
        ]


# ---- listă și detaliu --------------------------------------------------------------------------------------------------------


def test_lista_este_goala_cand_nu_e_nimic(client: TestClient, proprietar: Cont) -> None:
    r = client.get("/alerte")
    assert r.status_code == 200 and "Nicio alertă deschisă" in r.text
    assert "Niciun worker nu a dat semn" in r.text


def test_lista_grupeaza_pe_cauza_si_arata_workerul(
    client: TestClient, proprietar: Cont, porneste_executor: Pornire, admin_engine: Engine
) -> None:
    porneste_executor()
    a = job_esuat(admin_engine, flux.esueaza, "p1")
    b = job_esuat(admin_engine, flux.esueaza, "p2")
    job_esuat(admin_engine, flux.esueaza_alt, "p3")
    w = watchdog()
    w.porneste()
    try:
        html = client.get("/alerte").text
    finally:
        w.opreste()
    assert html.count('<section class="card" aria-labelledby="g-') == 2, "două cauze, două grupuri"
    assert "2 intrări" in html and "1 intrare" in html
    assert f'href="/alerte/{a.id}"' in html and f'href="/alerte/{b.id}"' in html
    assert "Minor" in html and a.cauza in html
    assert "worker-local" in html and "activ" in html


def test_intrarile_inchise_apar_doar_la_toate(
    client: TestClient, proprietar: Cont, porneste_executor: Pornire, admin_engine: Engine
) -> None:
    porneste_executor()
    i = job_esuat(admin_engine, flux.esueaza, "q1")
    with sesiune_agentie() as db:
        coada_erori.inchide(db, db.get(IntrareEroare, i.id), motiv="cunoscut", utilizator_id=None)  # type: ignore[arg-type]
    assert f"/alerte/{i.id}" not in client.get("/alerte").text
    assert f"/alerte/{i.id}" in client.get("/alerte?stare=toate").text


def test_detaliul_arata_contextul_complet(
    client: TestClient, proprietar: Cont, porneste_executor: Pornire, admin_engine: Engine
) -> None:
    porneste_executor()
    i = job_esuat(admin_engine, flux.esueaza, "d1")
    r = client.get(f"/alerte/{i.id}")
    assert r.status_code == 200
    for fragment in (
        "watchdog.esueaza",
        "watchdog.pas_stricat",
        "EroareDefinitiva",
        "nu merge jobul d1",
        "watchdog.pas_bun",
        "Ce s-a încercat",
        "eroare definitivă",
        "Argumentele jobului",
        i.cauza,
        i.workflow_id,
        f'action="/alerte/{i.id}/reia"',
        f'action="/alerte/{i.id}/inchide"',
        'name="csrf_token"',
    ):
        assert fragment in r.text, fragment


@pytest.mark.parametrize("id_intrare", ["nu-e-uuid", "00000000-0000-4000-8000-000000000000"])
def test_intrare_inexistenta_este_404(client: TestClient, proprietar: Cont, id_intrare: str) -> None:
    assert client.get(f"/alerte/{id_intrare}").status_code == 404


def test_pe_acasa_se_vad_alertele_deschise_si_workerul(
    client: TestClient, proprietar: Cont, porneste_executor: Pornire, admin_engine: Engine
) -> None:
    assert "niciuna" in client.get("/").text
    porneste_executor()
    job_esuat(admin_engine, flux.esueaza, "h1")
    w = watchdog()
    w.porneste()
    try:
        html = client.get("/").text
    finally:
        w.opreste()
    assert 'href="/alerte"' in html and "Alerte deschise" in html and "Worker worker-local" in html


# ---- închide ----------------------------------------------------------------------------------------------------------------------


def test_inchiderea_cere_csrf_motiv_si_scrie_auditul(
    client: TestClient, proprietar: Cont, porneste_executor: Pornire, admin_engine: Engine
) -> None:
    porneste_executor()
    i = job_esuat(admin_engine, flux.esueaza, "i1")
    cale = f"/alerte/{i.id}/inchide"
    assert client.post(cale, data={"motiv": "cunoscut"}).status_code == 403, "fără jeton CSRF"
    assert intrare(i.workflow_id).stare == "noua"
    jeton = csrf(client, f"/alerte/{i.id}")
    r = client.post(cale, data={"motiv": "  ", "csrf_token": jeton})
    assert r.status_code == 422 and "motivul" in r.text
    assert intrare(i.workflow_id).stare == "noua"

    r = client.post(
        cale, data={"motiv": "cunoscută, se rezolvă în F9", "csrf_token": jeton}, follow_redirects=False
    )
    assert r.status_code == 303 and r.headers["location"] == f"/alerte/{i.id}?mesaj=inchis"
    inchisa = intrare(i.workflow_id)
    assert inchisa.stare == "inchisa" and inchisa.inchis_de == proprietar.id
    assert inchisa.motiv_inchidere == "cunoscută, se rezolvă în F9" and inchisa.inchis_la is not None

    (a,) = audit(admin_engine, "alerte.inchide", i.id)
    assert a["obiect_id"] == str(i.id) and a["utilizator_id"] == proprietar.id
    assert a["detalii"]["motiv"] == "cunoscută, se rezolvă în F9" and a["detalii"]["job"] == i.workflow_id  # type: ignore[index]
    assert "închisă și decizia" in client.get(f"/alerte/{i.id}?mesaj=inchis").text

    assert client.post(cale, data={"motiv": "din nou", "csrf_token": jeton}).status_code == 409
    assert client.post(f"/alerte/{i.id}/reia", data={"csrf_token": jeton}).status_code == 409
    with admin_engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM coada_erori")).scalar_one() == 1, "nimic nu s-a șters"


# ---- reia -------------------------------------------------------------------------------------------------------------------------


def test_reluarea_unui_job_care_se_poate_repara_il_termina_si_inchide_intrarea(
    client: TestClient, proprietar: Cont, porneste_executor: Pornire, admin_engine: Engine
) -> None:
    porneste_executor()
    flux.ESUEAZA_PRIMELE["rp1"] = 1
    i = job_esuat(admin_engine, flux.capricios, "rp1")
    cale = f"/alerte/{i.id}/reia"
    assert client.post(cale).status_code == 403, "fără jeton CSRF"
    assert intrare(i.workflow_id).stare == "noua"

    jeton = csrf(client, f"/alerte/{i.id}")
    r = client.post(cale, data={"csrf_token": jeton}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/alerte/{i.id}?mesaj=reluat"
    reluata = intrare(i.workflow_id)
    assert reluata.stare == "reluata" and reluata.reluari == 1 and reluata.reluat_ca
    (a,) = audit(admin_engine, "alerte.reia", i.id)
    assert a["obiect_id"] == str(i.id) and a["utilizator_id"] == proprietar.id
    assert a["detalii"]["continua_ca"] == reluata.reluat_ca  # type: ignore[index]

    assert motor.asteapta_flux(reluata.reluat_ca, timeout_sec=20).stare is motor.StareJob.TERMINAT
    assert flux.incercari("rp1") == 2
    watchdog().scaneaza()
    inchisa = intrare(i.workflow_id)
    assert inchisa.stare == "inchisa" and inchisa.motiv_inchidere == "reluat și terminat cu succes"
    assert inchisa.inchis_de is None, "închisă de sistem, nu de un om"
    assert "închisă automat" in client.get(f"/alerte/{i.id}").text


def test_reluarea_care_esueaza_din_nou_creeaza_o_intrare_noua_cu_aceeasi_cauza(
    client: TestClient, proprietar: Cont, porneste_executor: Pornire, admin_engine: Engine
) -> None:
    porneste_executor()
    i = job_esuat(admin_engine, flux.esueaza, "rp2")  # eșuează mereu
    jeton = csrf(client, f"/alerte/{i.id}")
    client.post(f"/alerte/{i.id}/reia", data={"csrf_token": jeton})
    fork = intrare(i.workflow_id).reluat_ca
    assert fork and motor.asteapta_flux(fork, timeout_sec=20).stare is motor.StareJob.ESUAT
    watchdog().scaneaza()

    veche, noua = intrare(i.workflow_id), intrare(fork)
    assert veche.stare == "inchisa" and "a eșuat" in (veche.motiv_inchidere or "")
    assert noua.stare == "noua" and noua.cauza == veche.cauza, "aceeași cauză, deci același grup"
    assert noua.context["bifurcat_din"] == i.workflow_id
    assert any("este o reluare" in x for x in noua.context["ce_s_a_incercat"])
    html = client.get("/alerte").text
    assert "1 intrare" in html and f"/alerte/{noua.id}" in html


def test_reluarea_de_la_un_pas_ales(
    client: TestClient, proprietar: Cont, porneste_executor: Pornire, admin_engine: Engine
) -> None:
    porneste_executor()
    flux.ESUEAZA_PRIMELE["rp3"] = 1
    i = job_esuat(admin_engine, flux.capricios, "rp3")
    jeton = csrf(client, f"/alerte/{i.id}")
    assert (
        client.post(f"/alerte/{i.id}/reia", data={"csrf_token": jeton, "de_la_pas": "abc"}).status_code == 422
    )
    r = client.post(
        f"/alerte/{i.id}/reia", data={"csrf_token": jeton, "de_la_pas": "1"}, follow_redirects=False
    )
    assert r.status_code == 303
    fork = intrare(i.workflow_id).reluat_ca
    assert fork and motor.asteapta_flux(fork, timeout_sec=20).stare is motor.StareJob.TERMINAT
    pasi = {p.nume for p in motor.pasi_job(fork)}
    assert "watchdog.pas_bun" in pasi, "pasul ales (1) a fost reluat"


def test_reluarea_unui_job_care_nu_mai_poate_fi_reluat_da_409(
    client: TestClient, proprietar: Cont, porneste_executor: Pornire, admin_engine: Engine
) -> None:
    porneste_executor()
    i = job_esuat(admin_engine, flux.esueaza, "rp4")
    with admin_engine.begin() as c:  # jobul a fost șters din baza motorului (retenție)
        c.execute(text("DELETE FROM dbos.workflow_status WHERE workflow_uuid = :w"), {"w": i.workflow_id})
    jeton = csrf(client, f"/alerte/{i.id}")
    r = client.post(f"/alerte/{i.id}/reia", data={"csrf_token": jeton})
    assert r.status_code == 409 and "nu mai există" in r.text
    assert intrare(i.workflow_id).stare == "noua", "o reluare eșuată nu schimbă intrarea"
    assert audit(admin_engine, "alerte.reia", i.id) == []


# ---- permisiuni ---------------------------------------------------------------------------------------------------------------------


def test_analistul_citeste_dar_nu_poate_reia_sau_inchide(
    client: TestClient,
    fabrica_conturi: Fabrica,
    ceas: dict[str, float],
    porneste_executor: Pornire,
    admin_engine: Engine,
) -> None:
    porneste_executor()
    i = job_esuat(admin_engine, flux.esueaza, "an1")
    analist = fabrica_conturi(Rol.ANALIST, cu_totp=True)
    autentifica(client, analist, ceas)
    assert client.get("/alerte").status_code == 200
    # un analist fără client activ nu vede intrările clientului (izolare); proprietarul le vede
    assert client.get(f"/alerte/{i.id}").status_code == 404
    jeton = csrf(client, "/meniu")
    assert (
        client.post(f"/alerte/{i.id}/inchide", data={"motiv": "x y z", "csrf_token": jeton}).status_code
        == 403
    )
    assert client.post(f"/alerte/{i.id}/reia", data={"csrf_token": jeton}).status_code == 403
    assert intrare(i.workflow_id).stare == "noua"


def test_operatorul_are_voie_dar_nu_vede_erorile_de_sistem(
    client: TestClient,
    fabrica_conturi: Fabrica,
    ceas: dict[str, float],
    porneste_executor: Pornire,
    admin_engine: Engine,
) -> None:
    porneste_executor()
    job = motor.trimite(
        flux.esueaza, str(uuid.uuid4()), "op1", cheie="ap-op1"
    )  # client necunoscut: eroare de sistem
    motor.asteapta_flux(job, timeout_sec=20)
    watchdog().scaneaza()
    i = intrare(job)
    assert i.tenant_id is None
    operator = fabrica_conturi(Rol.OPERATOR, cu_totp=True)
    autentifica(client, operator, ceas)
    assert client.get("/alerte").status_code == 200
    assert client.get(f"/alerte/{i.id}").status_code == 404, (
        "intrările de sistem sunt doar ale proprietarului"
    )
    jeton = csrf(client, "/meniu")
    assert (
        client.post(f"/alerte/{i.id}/inchide", data={"motiv": "încerc", "csrf_token": jeton}).status_code
        == 404
    )
    assert intrare(job).stare == "noua"


@pytest.mark.parametrize("rol", [Rol.CLIENT_TITULAR, Rol.CLIENT_APROBATOR, Rol.CLIENT_VIZITATOR])
def test_clientii_nu_au_acces(client: TestClient, fabrica_conturi: Fabrica, rol: Rol) -> None:
    from tests.integration.conftest import login

    cont = fabrica_conturi(rol)
    login(client, cont.email, cont.parola)
    assert client.get("/alerte").status_code == 403
    assert client.post(
        "/alerte/00000000-0000-4000-8000-000000000000/inchide", data={"motiv": "x"}
    ).status_code in (403,)
