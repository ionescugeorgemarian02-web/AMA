"""F3.1 — registrul de furnizori și modele: sămânța din inventar, activarea (uz comercial, cheie) și ecranul."""

import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app import gateway
from app.conturi import Rol
from app.db import sesiune_agentie
from app.gateway import inventar
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf

pytestmark = pytest.mark.db
Fabrica = Callable[..., Cont]
CHEIE_DE_TEST = "cheie-de-proba-NU-TREBUIE-SA-APARA-NICAIERI-123456"  # nu e o cheie reală


@pytest.fixture(autouse=True)
def _registru_curat(admin_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for f in inventar.FURNIZORI:
        monkeypatch.delenv(f.cheie_env, raising=False)
    with admin_engine.begin() as c:
        c.execute(text("UPDATE gateway_furnizori SET stare = 'inactiv', stare_motiv = ''"))
    yield
    with admin_engine.begin() as c:
        c.execute(text("UPDATE gateway_furnizori SET stare = 'inactiv', stare_motiv = ''"))


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


def _id(cod: str) -> uuid.UUID:
    with sesiune_agentie() as db:
        f = gateway.furnizor(db, cod)
        assert f is not None
        return f.id


def test_furnizorii_din_inventar_sunt_in_registru_cu_limite_si_termeni() -> None:
    with sesiune_agentie() as db:
        fs = {f.cod: f for f in gateway.furnizori(db)}
        assert set(fs) >= {f.cod for f in inventar.FURNIZORI}
        assert (fs["openrouter"].cereri_minut, fs["openrouter"].cereri_zi) == (20, 50)
        assert fs["gemini"].uz_comercial is False and fs["gemini"].marcaj == "V"
        assert fs["anthropic"].platit is True
        groq = {m.identificator: m for m in gateway.modele(db, furnizor_id=fs["groq"].id)}
        m = groq["llama-3.3-70b-versatile"]
        assert (m.cereri_minut, m.cereri_zi, m.tokeni_zi) == (30, 1000, 200_000)
        assert m.nivel == "T3" and m.marcaj == "S" and m.verificat_la is not None
        assert all(f.stare == "inactiv" for f in fs.values())  # nimic nu pornește activ


def test_activarea_cere_uz_comercial_confirmat_si_cheie(monkeypatch: pytest.MonkeyPatch) -> None:
    with sesiune_agentie() as db, pytest.raises(gateway.NuSePoateActiva, match="Cheia lipsește"):
        gateway.activeaza(db, _id("groq"), utilizator_id=None)
    monkeypatch.setenv("AMA_CHEIE_GEMINI", CHEIE_DE_TEST)
    with sesiune_agentie() as db, pytest.raises(gateway.NuSePoateActiva, match="uz comercial"):
        gateway.activeaza(db, _id("gemini"), utilizator_id=None)  # cheia există, dar termenii nu permit
    monkeypatch.setenv("AMA_CHEIE_GROQ", CHEIE_DE_TEST)
    with sesiune_agentie() as db:
        f = gateway.activeaza(db, _id("groq"), utilizator_id=None)
        assert f.stare == "activ"
        f = gateway.dezactiveaza(db, f.id, motiv="test", utilizator_id=None)
        assert f.stare == "inactiv" and f.stare_motiv == "test"


def test_baza_refuza_activarea_fara_uz_comercial_si_numele_de_variabila_straine(admin_engine: Engine) -> None:
    with pytest.raises(DBAPIError, match="furnizor_activ_cere_uz_comercial"), admin_engine.begin() as c:
        c.execute(text("UPDATE gateway_furnizori SET stare = 'activ' WHERE cod = 'gemini'"))
    with pytest.raises(DBAPIError, match="cheie_env"), admin_engine.begin() as c:
        c.execute(text("UPDATE gateway_furnizori SET cheie_env = 'AMA_MASTER_KEY' WHERE cod = 'groq'"))
    with pytest.raises(DBAPIError, match="url_baza"), admin_engine.begin() as c:
        c.execute(text("UPDATE gateway_furnizori SET url_baza = 'http://exemplu.test' WHERE cod = 'groq'"))


def test_ecranul_arata_furnizorii_cu_limite_termeni_si_niciodata_cheia(
    client: TestClient, proprietar: Cont, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AMA_CHEIE_GROQ", CHEIE_DE_TEST)
    r = client.get("/gateway/registru")
    assert r.status_code == 200
    for f in inventar.FURNIZORI:
        assert f.nume.split(" (")[0].split(" ")[0] in r.text
    assert "20 cereri/min, 50 cereri/zi" in r.text  # limitele OpenRouter
    assert "30 cereri/min, 1.000 cereri/zi, 200.000 tokeni/zi" in r.text  # limitele modelului Groq
    assert "Uz comercial" in r.text and "Date folosite la antrenare" in r.text
    assert "[V] verificat la sursă" in r.text and "2026-11-10" in r.text
    assert "configurată" in r.text and "AMA_CHEIE_GROQ" in r.text
    assert CHEIE_DE_TEST not in r.text


def test_proprietarul_activeaza_si_dezactiveaza_cu_audit_fara_cheie(
    client: TestClient, proprietar: Cont, monkeypatch: pytest.MonkeyPatch, admin_engine: Engine
) -> None:
    monkeypatch.setenv("AMA_CHEIE_GROQ", CHEIE_DE_TEST)
    fid = _id("groq")
    jeton = csrf(client, "/gateway/registru")
    r = client.post(f"/gateway/furnizori/{fid}/activeaza", data={"csrf_token": jeton}, follow_redirects=False)
    assert r.status_code == 303 and "mesaj=activat" in r.headers["location"]
    assert "activ" in client.get("/gateway/registru").text
    with sesiune_agentie() as db:
        f = gateway.furnizor(db, "groq")
        assert f is not None and f.stare == "activ"
    r = client.post(
        f"/gateway/furnizori/{fid}/dezactiveaza",
        data={"csrf_token": jeton, "motiv": "pauză"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with admin_engine.connect() as c:
        randuri = c.execute(
            text(
                "SELECT actiune, utilizator_id, detalii::text AS d FROM jurnal_audit WHERE obiect_id = 'groq' ORDER BY creat_la"
            )
        ).all()
    assert [r.actiune for r in randuri][-2:] == ["gateway.furnizor_activat", "gateway.furnizor_dezactivat"]
    assert all(r.utilizator_id == proprietar.id for r in randuri[-2:])
    assert all(CHEIE_DE_TEST not in r.d for r in randuri)


def test_activarea_refuzata_se_vede_in_ecran_si_in_audit(
    client: TestClient, proprietar: Cont, admin_engine: Engine
) -> None:
    jeton = csrf(client, "/gateway/registru")
    r = client.post(
        f"/gateway/furnizori/{_id('gemini')}/activeaza", data={"csrf_token": jeton}, follow_redirects=True
    )
    assert r.status_code == 200 and "Uzul comercial" in r.text
    with admin_engine.connect() as c:
        n = c.execute(
            text(
                "SELECT count(*) FROM jurnal_audit WHERE actiune = 'gateway.furnizor_activare_refuzata' AND obiect_id = 'gemini'"
            )
        ).scalar_one()
    assert n >= 1
    with sesiune_agentie() as db:
        f = gateway.furnizor(db, "gemini")
        assert f is not None and f.stare == "inactiv"


def test_operatorul_citeste_dar_nu_schimba_si_fara_csrf_se_respinge(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float], proprietar: Cont
) -> None:
    fid = _id("groq")
    jeton = csrf(client, "/gateway/registru")
    assert client.post(f"/gateway/furnizori/{fid}/activeaza", data={}).status_code == 403  # fără CSRF
    client.cookies.clear()
    operator = fabrica_conturi(Rol.OPERATOR, cu_totp=True)
    autentifica(client, operator, ceas)
    r = client.get("/gateway/registru")
    assert r.status_code == 200 and "Activează" not in r.text
    jeton = csrf(client, "/gateway/registru")
    assert client.post(f"/gateway/furnizori/{fid}/activeaza", data={"csrf_token": jeton}).status_code == 403


def test_clientul_nu_vede_registrul(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]
) -> None:
    titular = fabrica_conturi(Rol.CLIENT_TITULAR, cu_totp=True)
    autentifica(client, titular, ceas)
    assert client.get("/gateway/registru").status_code == 403
