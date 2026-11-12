"""F3.7 „Gata când”: orice apel se vede în panou, cu prompt, model, tokeni, durată și preț-umbră (listă + detaliu,
filtre pe client / model / rezultat), respectând izolarea."""

import re
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app import gateway
from app.conturi import Rol
from app.db import sesiune_tenant
from app.operare.motor import Prioritate
from tests.furnizor_fals import FurnizorFals
from tests.gateway_utile import CHEIE_PROBA, Clasificare, FabricaModele, gazda
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica

pytestmark = pytest.mark.db
Fabrica = Callable[..., Cont]


@pytest.fixture(autouse=True)
def _mediu(cheie_proba: str, ceas_controlat: object, fals: FurnizorFals) -> None:
    fals.text = '{"eticheta": "pozitiv", "dovezi": [], "incredere": 0.8}'
    fals.tokeni = (1234, 56)


@pytest.fixture
def mediu(fabrica_modele: FabricaModele) -> tuple[FabricaModele, str, Any, Any]:
    a = fabrica_modele.model(
        fabrica_modele.furnizor(), identificator="ma", pret_umbra_intrare=1.0, pret_umbra_iesire=2.0
    )
    b = fabrica_modele.model(fabrica_modele.furnizor(), identificator="mb")
    prompt = fabrica_modele.prompt(fabrica_modele.profil([a.cod, b.cod]))
    return fabrica_modele, prompt, a, b


def apeleaza(tenant: uuid.UUID, prompt: str, text_: str = "salut") -> gateway.Rezultat:
    with sesiune_tenant(tenant) as db:
        return gateway.apeleaza(
            db, prompt=prompt, variabile={"text": text_}, schema=Clasificare, tenant_id=tenant,
            componenta="h4.moderator", prioritate=Prioritate.P2,
        )  # fmt: skip


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


def randuri(html: str, prompt: str) -> list[str]:
    return [r for r in re.findall(r"<tr>.*?</tr>", html, re.S) if prompt in r]


def test_lista_arata_fiecare_apel_cu_prompt_model_tokeni_durata_si_pret_umbra(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, mediu: Any
) -> None:
    _, prompt, a, _ = mediu
    r = apeleaza(tenant, prompt)
    html = client.get("/gateway/apeluri").text
    [rand] = randuri(html, prompt)
    assert f"{prompt} v1" in rand and a.cod in rand and "reușit" in rand and "h4.moderator" in rand
    assert "1234 / 56" in rand and " ms" in rand and "0.001346" in rand  # 1234 × 1 + 56 × 2 la 1 mil.
    assert f"/gateway/apeluri/{r.apel_id}" in rand


def test_detaliul_arata_promptul_trimis_raspunsul_si_traseul(
    client: TestClient,
    proprietar: Cont,
    tenant: uuid.UUID,
    mediu: Any,
    fals: FurnizorFals,
    admin_engine: Engine,
) -> None:
    _, prompt, a, b = mediu
    fals.scenariu(gazda(a), "5xx", "5xx", "5xx", "5xx")
    r = apeleaza(tenant, prompt, "textul <script>alert(1)</script> al clientului")
    html = client.get(f"/gateway/apeluri/{r.apel_id}").text
    assert b.cod in html and "Ești un clasificator atent." in html
    assert "Clasifică textul: textul &lt;script&gt;alert(1)&lt;/script&gt; al clientului" in html  # evadat
    assert "<script>alert(1)" not in html
    assert "&#34;eticheta&#34;: &#34;pozitiv&#34;" in html or '"eticheta": "pozitiv"' in html
    assert a.cod in html and "server" in html  # traseul: a căzut, a răspuns rezerva
    assert "0.001" in html or ("0.00" in html and "USD" in html)
    assert CHEIE_PROBA not in html
    with admin_engine.connect() as c:
        n = c.execute(
            text("SELECT count(*) FROM jurnal_audit WHERE actiune = 'gateway.apel_citit' AND obiect_id = :i"),
            {"i": str(r.apel_id)},
        ).scalar_one()
    assert n == 1  # deschiderea conținutului lasă urmă


def test_filtre_pe_client_model_si_rezultat(
    client: TestClient,
    proprietar: Cont,
    fabrica_clienti: Any,
    tenant: uuid.UUID,
    mediu: Any,
    fals: FurnizorFals,
) -> None:
    _fabrica, prompt, a, b = mediu
    alt = fabrica_clienti()
    apeleaza(tenant, prompt)
    apeleaza(alt, prompt)
    fals.scenariu(gazda(a), permanent="5xx")
    fals.scenariu(gazda(b), permanent="5xx")
    with pytest.raises(gateway.Amanat):
        apeleaza(tenant, prompt)
    html = client.get("/gateway/apeluri").text
    assert len(randuri(html, prompt)) == 3  # proprietarul vede toți clienții
    assert len(randuri(client.get(f"/gateway/apeluri?client={alt}").text, prompt)) == 1
    assert len(randuri(client.get(f"/gateway/apeluri?client={tenant}").text, prompt)) == 2
    amanate = randuri(client.get("/gateway/apeluri?rezultat=amanat").text, prompt)
    assert len(amanate) == 1 and "amânat" in amanate[0]
    assert len(randuri(client.get("/gateway/apeluri?rezultat=ok").text, prompt)) == 2
    assert len(randuri(client.get(f"/gateway/apeluri?model={b.identificator}&rezultat=ok").text, prompt)) == 0
    assert len(randuri(client.get(f"/gateway/apeluri?model={a.identificator}&rezultat=ok").text, prompt)) == 2
    assert (
        "Niciun apel" in client.get("/gateway/apeluri?model=%25nu_exista").text
    )  # `%` din filtru nu e metacaracter
    assert client.get("/gateway/apeluri?client=nu-este-uuid&rezultat=oricare").status_code == 200


def test_operatorul_vede_doar_clientul_lui_iar_apelul_altui_client_nu_exista(
    client: TestClient,
    fabrica_conturi: Fabrica,
    ceas: dict[str, float],
    fabrica_clienti: Any,
    mediu: Any,
    admin_engine: Engine,
) -> None:
    _, prompt, _, _ = mediu
    a, b = fabrica_clienti(), fabrica_clienti()
    r_a, r_b = apeleaza(a, prompt), apeleaza(b, prompt)
    operator = fabrica_conturi(Rol.OPERATOR, cu_totp=True)
    with admin_engine.begin() as c:
        c.execute(
            text("INSERT INTO alocari (id, utilizator_id, tenant_id) VALUES (gen_random_uuid(), :u, :t)"),
            {"u": operator.id, "t": a},
        )
    autentifica(client, operator, ceas)
    lista = client.get("/gateway/apeluri").text
    # fără client activ, operatorul nu vede nimic din jurnal (refuz implicit)
    assert not randuri(lista, prompt) or f"/gateway/apeluri/{r_b.apel_id}" not in lista
    assert client.get(f"/gateway/apeluri/{r_b.apel_id}").status_code == 404
    assert client.get(f"/gateway/apeluri/{uuid.uuid4()}").status_code == 404
    assert r_a.apel_id is not None


def test_clientul_nu_vede_ecranul(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]
) -> None:
    titular = fabrica_conturi(Rol.CLIENT_TITULAR, cu_totp=True)
    autentifica(client, titular, ceas)
    assert client.get("/gateway/apeluri").status_code == 403


def test_continut_expirat_se_afiseaza_ca_atare(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, mediu: Any, admin_engine: Engine
) -> None:
    _, prompt, _, _ = mediu
    r = apeleaza(tenant, prompt)
    with admin_engine.begin() as c:
        c.execute(text("DELETE FROM gateway_apeluri_continut WHERE apel_id = :i"), {"i": r.apel_id})
    html = client.get(f"/gateway/apeluri/{r.apel_id}").text
    assert "Conținutul nu mai este păstrat" in html and prompt in html
