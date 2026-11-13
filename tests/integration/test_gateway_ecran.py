"""F3.10 — ecranul „Modele și cote”: cota rămasă pe fiecare furnizor / model, întrerupătoare, scoruri, viteza locală, consumul
pe client față de buget, editarea de către proprietar (CSRF, permisiune, audit). „Gata când”: vezi cota rămasă pe fiecare
furnizor și consumul pe client."""

import re
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app import gateway
from app.conturi import Rol
from app.db import sesiune_agentie, sesiune_tenant
from app.operare.motor import Prioritate
from tests.furnizor_fals import FurnizorFals
from tests.gateway_utile import CeasControlat, FabricaModele
from tests.integration.conftest import Cont
from tests.integration.test_gateway_apeluri import apeleaza
from tests.integration.utile_panou import autentifica, csrf

pytestmark = pytest.mark.db
Fabrica = Callable[..., Cont]


@pytest.fixture(autouse=True)
def _mediu(cheie_proba: str, ceas_controlat: CeasControlat, fals: FurnizorFals) -> None:
    fals.text = '{"eticheta": "pozitiv", "dovezi": [], "incredere": 0.8}'
    fals.tokeni = (100, 50)
    fals.antete_limita = False  # contoarele rămân ale noastre


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


class Mediu:
    def __init__(self, f: FabricaModele) -> None:
        self.fid = f.furnizor(cereri_zi=100, tokeni_zi=10_000, cereri_minut=10)
        self.a = f.model(self.fid, identificator="ecran-a", cereri_zi=40)
        self.prompt = f.prompt(f.profil([self.a.cod]))


@pytest.fixture
def mediu(fabrica_modele: FabricaModele) -> Mediu:
    return Mediu(fabrica_modele)


def sectiune(html: str, cod: str) -> str:
    m = re.search(rf'<section class="card" aria-labelledby="f-{cod}">.*?</section>', html, re.S)
    assert m, cod
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group()))


def test_se_vede_cota_ramasa_pe_fiecare_furnizor_si_pe_model_cu_resetare(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, mediu: Mediu
) -> None:
    for _ in range(3):
        apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)
    cod = mediu.a.furnizor
    text_ = sectiune(client.get("/gateway/registru").text, cod)
    assert "model · zi: 37 din 40 cereri rămase" in text_  # 40 − 3 apeluri
    assert (
        "cont · zi: 97 din 100 cereri rămase" in text_ and "9.550 din 10.000 tokeni rămași" in text_
    )  # 10 000 − 3 × 150
    assert "cont · minut: 7 din 10 cereri rămase" in text_
    assert "resetare 13.11 00:00 UTC" in text_ and "resetare 12.11 12:01 UTC" in text_
    # fiecare furnizor din registru (inclusiv sămânța) are secțiune și stare de întrerupător
    html = client.get("/gateway/registru").text
    for f in ("openrouter", "groq", "gemini", "cloudflare", "anthropic", "local", "vectori"):
        assert f'aria-labelledby="f-{f}"' in html
    assert html.count("Întrerupător") >= 7 and "Cota rămasă" in html


def test_o_cota_epuizata_si_un_intrerupator_deschis_se_vad(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, fabrica_modele: FabricaModele, fals: FurnizorFals
) -> None:
    f = fabrica_modele.furnizor(cereri_zi=2)
    m = fabrica_modele.model(f, identificator="strans")
    prompt = fabrica_modele.prompt(fabrica_modele.profil([m.cod]))
    apeleaza(tenant, prompt, prioritate=Prioritate.P0)
    apeleaza(tenant, prompt, prioritate=Prioritate.P0)
    t = sectiune(client.get("/gateway/registru").text, m.furnizor)
    assert "0 din 2 cereri rămase" in t and "epuizată" in t
    g = fabrica_modele.furnizor()
    n = fabrica_modele.model(g, identificator="cazut")
    p2 = fabrica_modele.prompt(fabrica_modele.profil([n.cod]))
    fals.scenariu(f"{n.furnizor}.exemplu.test", permanent="5xx")
    with pytest.raises(gateway.Amanat):
        apeleaza(tenant, p2, prioritate=Prioritate.P2)
    t2 = sectiune(client.get("/gateway/registru").text, n.furnizor)
    assert "deschis" in t2 and "până la 12.11 12:02 UTC" in t2


def test_scorurile_viteza_locala_si_rularile_se_vad(
    client: TestClient, proprietar: Cont, fabrica_modele: FabricaModele, admin_engine: Engine
) -> None:
    f = fabrica_modele.furnizor()
    m = fabrica_modele.model(f, identificator="scorat", scor={"creatie": 0.8123, "strategie": 0.5})
    fl = fabrica_modele.furnizor(tip_api="local", cod=f"loc{uuid.uuid4().hex[:8]}")
    loc = fabrica_modele.model(fl, identificator="local-x", nivel="local")
    with admin_engine.begin() as c:
        c.execute(
            text(
                "UPDATE gateway_modele SET tokeni_pe_secunda = 7.25, viteza_masurata_la = now() WHERE id = :i"
            ),
            {"i": loc.model_id},
        )
    html = client.get("/gateway/registru").text
    rand = re.search(rf"<tr><td><code>{re.escape(m.cod)}</code></td>.*?</tr>", html, re.S)
    assert rand and "0.8123" in rand.group() and "0.5" in rand.group()
    assert "7.25 tokeni/s" in html


def test_consumul_pe_client_arata_azi_si_luna_fata_de_buget(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, mediu: Mediu, admin_engine: Engine
) -> None:
    with sesiune_agentie() as db:
        gateway.bugete.seteaza_client(
            db, tenant, {"apeluri_zi": 50, "apeluri_luna": 700}, utilizator_id=proprietar.id
        )
    apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)
    apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)
    # numele clienților de probă pornesc de la prefixul unui UUID de timp (același ~4,6 minute): nu identifică
    # clientul, deci testul își dă un nume unic înainte să citească ecranul
    nume = f"Firma unică {tenant.hex}"
    with admin_engine.begin() as c:
        c.execute(text("UPDATE clienti SET nume = :n WHERE id = :t"), {"n": nume, "t": tenant})
    html = client.get("/gateway/registru").text
    randuri = [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r))
        for r in re.findall(r"<tr>.*?</tr>", html, re.S)
        if nume in r
    ]
    plat = next(r for r in randuri if "buget propriu" in r)
    assert "buget propriu" in plat and "2 / 50 apeluri" in plat and "300 / 1.500.000 tokeni" in plat
    assert "2 / 700 apeluri" in plat  # luna


# --- editare de către proprietar


def test_proprietarul_schimba_limitele_cu_audit_iar_apelurile_urmeaza_noua_limita(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, mediu: Mediu, admin_engine: Engine
) -> None:
    jeton = csrf(client, "/gateway/registru")
    r = client.post(
        f"/gateway/modele/{mediu.a.model_id}/limite",
        data={"csrf_token": jeton, "cereri_minut": "", "cereri_zi": "1", "tokeni_minut": "", "tokeni_zi": ""},
        follow_redirects=False,
    )
    assert r.status_code == 303 and "mesaj=limite" in r.headers["location"]
    apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P0)  # P0 poate folosi toată limita (1)
    with pytest.raises(gateway.Amanat):
        apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P0)
    r = client.post(
        f"/gateway/furnizori/{mediu.fid}/limite",
        data={"csrf_token": jeton, "cereri_minut": "5", "cereri_zi": "1.000", "tokeni_minut": "", "tokeni_zi": "",
              "reset_zi_ora": "6"},
        follow_redirects=False,
    )  # fmt: skip
    assert r.status_code == 303
    with admin_engine.connect() as c:
        f = c.execute(
            text(
                "SELECT cereri_minut, cereri_zi, tokeni_zi, reset_zi_ora FROM gateway_furnizori WHERE id = :i"
            ),
            {"i": mediu.fid},
        ).one()
        audit = c.execute(
            text(
                "SELECT utilizator_id, detalii::text FROM jurnal_audit WHERE actiune = 'gateway.limite_setate' ORDER BY creat_la"
            )
        ).all()
    assert tuple(f) == (5, 1000, None, 6)
    assert len(audit) == 2 and all(a[0] == proprietar.id for a in audit) and "jetoane" in audit[1][1]


@pytest.mark.parametrize(
    ("camp", "valoare"),
    [("cereri_zi", "-5"), ("cereri_zi", "abc"), ("tokeni_zi", "0"), ("reset_zi_ora", "30")],
)
def test_valorile_nepermise_nu_se_salveaza(
    client: TestClient, proprietar: Cont, mediu: Mediu, camp: str, valoare: str
) -> None:
    jeton = csrf(client, "/gateway/registru")
    data = {"csrf_token": jeton, "cereri_zi": "7", camp: valoare}
    r = client.post(f"/gateway/furnizori/{mediu.fid}/limite", data=data, follow_redirects=True)
    assert r.status_code == 200 and "mesaj eroare" in r.text
    with sesiune_agentie() as db:
        f = gateway.furnizori(db)
        assert next(x for x in f if x.id == mediu.fid).cereri_zi == 100  # neschimbat


def test_termenii_se_editeaza_dar_un_furnizor_activ_nu_poate_pierde_uzul_comercial(
    client: TestClient, proprietar: Cont, mediu: Mediu, admin_engine: Engine
) -> None:
    jeton = csrf(client, "/gateway/registru")
    ok = {"csrf_token": jeton, "uz_comercial": "da", "antrenare_pe_date": "nu", "restrictii_regionale": "doar UE",
          "marcaj": "V", "verificat_la": "2026-11-12"}  # fmt: skip
    r = client.post(f"/gateway/furnizori/{mediu.fid}/termeni", data=ok, follow_redirects=False)
    assert r.status_code == 303 and "mesaj=termeni" in r.headers["location"]
    with sesiune_agentie() as db:
        f = next(x for x in gateway.furnizori(db) if x.id == mediu.fid)
        assert (f.uz_comercial, f.antrenare_pe_date, f.restrictii_regionale, f.marcaj) == (
            True,
            False,
            "doar UE",
            "V",
        )
    r = client.post(
        f"/gateway/furnizori/{mediu.fid}/termeni", data={**ok, "uz_comercial": "nu"}, follow_redirects=True
    )
    assert "mesaj eroare" in r.text and "dezactivează-l" in r.text  # furnizorul de probă este activ
    r = client.post(
        f"/gateway/furnizori/{mediu.fid}/termeni", data={**ok, "verificat_la": ""}, follow_redirects=True
    )
    assert "cere data verificării" in r.text
    with admin_engine.connect() as c:
        n = c.execute(
            text("SELECT count(*) FROM jurnal_audit WHERE actiune = 'gateway.termeni_setati'")
        ).scalar_one()
    assert n >= 1


def test_bugetul_unui_client_si_cele_implicite_se_editeaza_din_ecran(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, admin_engine: Engine
) -> None:
    jeton = csrf(client, "/gateway/registru")
    camp = {"csrf_token": jeton, "apeluri_zi": "12", "tokeni_zi": "", "pret_umbra_zi": "0,75", "apeluri_luna": "",
            "tokeni_luna": "", "pret_umbra_luna": ""}  # fmt: skip
    r = client.post(f"/gateway/clienti/{tenant}/buget", data=camp, follow_redirects=False)
    assert r.status_code == 303 and "mesaj=buget" in r.headers["location"]
    with sesiune_tenant(tenant) as db:
        b = gateway.bugete.efectiv(db, tenant)
    assert (
        b.zi.apeluri == 12 and str(b.zi.pret_umbra) == "0.7500" and b.zi.tokeni == 1_500_000
    )  # restul: implicit
    gol = dict.fromkeys(camp, "") | {"csrf_token": jeton}
    client.post(f"/gateway/clienti/{tenant}/buget", data=gol, follow_redirects=False)  # revenire la implicit
    with sesiune_tenant(tenant) as db:
        assert gateway.bugete.efectiv(db, tenant).zi.apeluri == 400
    r = client.post(f"/gateway/clienti/{uuid.uuid4()}/buget", data=camp)
    assert r.status_code == 404
    rau = client.post(
        f"/gateway/clienti/{tenant}/buget", data={**camp, "apeluri_zi": "-1"}, follow_redirects=True
    )
    assert "mesaj eroare" in rau.text
    implicite = {**camp, "apeluri_zi": "400", "tokeni_zi": "1500000", "pret_umbra_zi": "1.50", "apeluri_luna": "8000",
                 "tokeni_luna": "30000000", "pret_umbra_luna": "30", "prag_avertizare": "85", "plafon_p1": "1.5"}  # fmt: skip
    assert client.post("/gateway/bugete/implicite", data=implicite, follow_redirects=False).status_code == 303
    with sesiune_agentie() as db:
        assert gateway.bugete.implicit(db).prag_avertizare == pytest.approx(0.85)
    client.post(
        "/gateway/bugete/implicite", data={**implicite, "prag_avertizare": "80"}, follow_redirects=False
    )
    bad = client.post(
        "/gateway/bugete/implicite", data={**implicite, "plafon_p1": "abc"}, follow_redirects=True
    )
    assert "mesaj eroare" in bad.text
    with admin_engine.connect() as c:
        n = c.execute(
            text(
                "SELECT count(*) FROM jurnal_audit WHERE actiune IN ('gateway.buget_client_setat','gateway.buget_implicit_setat')"
            )
        ).scalar_one()
    assert n >= 3


def test_testul_comparativ_se_porneste_si_notele_se_importa_din_ecran(
    client: TestClient, proprietar: Cont, fabrica_modele: FabricaModele, fals: FurnizorFals, motor_curat: None
) -> None:
    from app.gateway import evaluare
    from tests.integration.test_gateway_evaluare import furnizor_de_calitate

    m = fabrica_modele.model(fabrica_modele.furnizor(), identificator="de-evaluat", nivel="T2")
    jeton = csrf(client, "/gateway/registru")
    r = client.post(
        "/gateway/evaluare/porneste", data={"csrf_token": jeton, "model": m.cod}, follow_redirects=False
    )
    assert r.status_code == 303 and "mesaj=evaluare" in r.headers["location"]
    assert (
        client.post(
            "/gateway/evaluare/porneste", data={"csrf_token": jeton, "model": "x/nu-exista"}
        ).status_code
        == 404
    )
    fals.text = furnizor_de_calitate({f"{m.furnizor}.exemplu.test": "bun"})
    rulare = evaluare.ruleaza(m.cod, profiluri=["clasificare"], pe_profil=2)
    html = client.get("/gateway/registru").text
    assert m.cod in html and "2 / 2" in html and "Importă note" in html
    r = client.post(
        f"/gateway/evaluare/{rulare.id}/note",
        data={"csrf_token": jeton, "csv": "sarcina_id,nota\nclasificare-01,5\nclasificare-02,4"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and "mesaj=note" in r.headers["location"]
    bad = client.post(
        f"/gateway/evaluare/{rulare.id}/note",
        data={"csrf_token": jeton, "csv": "x,y\n1,2"},
        follow_redirects=True,
    )
    assert "mesaj eroare" in bad.text


def test_operatorul_vede_dar_nu_poate_edita_si_fara_csrf_se_respinge(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float], proprietar: Cont, mediu: Mediu
) -> None:
    fid = mediu.fid
    assert (
        client.post(f"/gateway/furnizori/{fid}/limite", data={"cereri_zi": "1"}).status_code == 403
    )  # fără CSRF
    client.cookies.clear()
    operator = fabrica_conturi(Rol.OPERATOR, cu_totp=True)
    autentifica(client, operator, ceas)
    r = client.get("/gateway/registru")
    assert r.status_code == 200 and "Cota rămasă" in r.text and "Consum pe client" in r.text
    assert "Salvează" not in r.text and "Pornește testul" not in r.text and "Importă notele" not in r.text
    jeton = csrf(client, "/gateway/registru")
    for url, data in (
        (f"/gateway/furnizori/{fid}/limite", {"cereri_zi": "1"}),
        (f"/gateway/modele/{mediu.a.model_id}/limite", {"cereri_zi": "1"}),
        (f"/gateway/furnizori/{fid}/termeni", {"marcaj": "I"}),
        (f"/gateway/clienti/{uuid.uuid4()}/buget", {}),
        ("/gateway/bugete/implicite", {}),
        ("/gateway/evaluare/porneste", {"model": "a/b"}),
    ):
        assert client.post(url, data={"csrf_token": jeton, **data}).status_code == 403, url


def test_nicio_cheie_in_ecran(client: TestClient, proprietar: Cont, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMA_CHEIE_GROQ", "cheie-de-proba-NU-TREBUIE-SA-APARA-NICAIERI-123456")
    assert "NU-TREBUIE-SA-APARA" not in client.get("/gateway/registru").text
    _: Any = None
