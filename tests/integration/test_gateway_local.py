"""F3.5 — modelul local și modelul de vectori. „Gata când” (în măsura verificabilă aici): o clasificare de
probă rulează prin adaptorul local, viteza se notează în registru prin comanda de măsurare, un vector se
calculează cât timp toate culoarele grele sunt ocupate (test real pe motor).

SIMULAT / NEVERIFICAT: nu există model local, nici rețea pentru a descărca unul. Serverul este un HTTP
fals în forma API-ului llama.cpp (`tests/server_local_fals.py`) sau furnizorul fals în proces; rularea
reală rămâne la migrarea pe VPS."""

import json
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, text

from app import gateway
from app.db import sesiune_agentie
from app.gateway import client, masurare, registru
from app.gateway.tipuri import Mesaj
from app.operare import motor
from app.operare.motor import Coada, Prioritate
from tests.furnizor_fals import FurnizorFals
from tests.gateway_utile import Clasificare, FabricaModele
from tests.integration import fluxuri_cozi as cozi
from tests.integration import fluxuri_local as flux
from tests.server_local_fals import ServerLocalFals

pytestmark = pytest.mark.db
Pornire = Callable[..., None]
LOCAL = "http://{cod}:8080/v1"


@pytest.fixture(autouse=True)
def _mediu(cheie_proba: str, ceas_controlat: object, fals: FurnizorFals) -> Iterator[None]:
    fals.text = '{"eticheta": "pozitiv", "dovezi": ["local"], "incredere": 0.8}'
    flux.reseteaza()
    cozi.reseteaza()
    yield
    cozi.elibereaza_tot()
    cozi.reseteaza()


def furnizor_local(f: FabricaModele) -> tuple[uuid.UUID, str]:
    cod = f"loc{uuid.uuid4().hex[:8]}"
    return f.furnizor(tip_api="local", cod=cod, url_baza=LOCAL.format(cod=cod)), cod


class Mediu:
    """Un furnizor la distanță (care va pica), un model local și un profil care degradează la local (ca
    „clasificare”)."""

    def __init__(self, f: FabricaModele) -> None:
        self.distant = f.model(f.furnizor(), identificator="distant", nivel="T1")
        fid, self.cod_local = furnizor_local(f)
        self.local = f.model(
            fid, identificator="local-3b", nivel="local", capabilitati=["iesire_structurata"]
        )
        self.profil = f.profil(
            [self.distant.cod], nivel_min="T1", la_epuizare="degradeaza", lant_degradare=["nivel:local"]
        )
        self.prompt = f.prompt(self.profil)


@pytest.fixture
def mediu(fabrica_modele: FabricaModele) -> Mediu:
    return Mediu(fabrica_modele)


def gazda_distant(m: Mediu) -> str:
    return f"{m.distant.furnizor}.exemplu.test"


# --- clasificarea prin adaptorul local


def test_o_clasificare_de_proba_ruleaza_prin_adaptorul_local_pe_coada_greu(
    tenant: uuid.UUID, mediu: Mediu, fals: FurnizorFals, porneste_executor: Pornire
) -> None:
    fals.scenariu(gazda_distant(mediu), permanent="5xx")  # furnizorul la distanță a căzut
    fals.timings = {"predicted_per_second": 12.5}
    porneste_executor(culoare_greu=2)
    job = motor.trimite(flux.clasifica, str(tenant), mediu.prompt, coada=Coada.GREU, cheie="local-greu")
    assert motor.asteapta_flux(job, timeout_sec=20).stare is motor.StareJob.TERMINAT
    assert [f"ok:{mediu.local.cod}:True"] == flux.REZULTATE  # degradat la local, marcat
    [cerere] = fals.cereri_la(mediu.cod_local)
    assert cerere.cale == "/v1/chat/completions"
    assert cerere.corp["response_format"]["type"] == "json_schema"  # decodare constrânsă de schemă
    assert cerere.corp["cache_prompt"] is True and cerere.corp["stream"] is False
    assert "authorization" not in {k.lower() for k in cerere.antete}  # fără cheie spre serverul intern


def test_modelul_local_nu_se_apeleaza_din_afara_culoarului_greu(
    tenant: uuid.UUID, mediu: Mediu, fals: FurnizorFals, porneste_executor: Pornire
) -> None:
    """Un job `io` nu poate lua modelul local: gateway-ul refuză cu un cod clar (fluxul își mută pasul pe
    `greu`)."""
    fals.scenariu(gazda_distant(mediu), permanent="5xx")
    porneste_executor()
    job = motor.trimite(flux.clasifica, str(tenant), mediu.prompt, coada=Coada.IO, cheie="local-io")
    assert motor.asteapta_flux(job, timeout_sec=20).stare is motor.StareJob.TERMINAT
    assert flux.REZULTATE == ["refuzat:local_doar_pe_coada_greu"]
    assert fals.cereri_la(mediu.cod_local) == []
    # și în afara oricărui job (script, proces web) la fel
    from tests.integration.test_gateway_apeluri import apeleaza

    with pytest.raises(gateway.ApelRefuzat) as exc:
        apeleaza(tenant, mediu.prompt, prioritate=Prioritate.P2)
    assert exc.value.cod == "local_doar_pe_coada_greu"


def test_modelele_de_vectori_nu_intra_in_lanturile_de_text(
    tenant: uuid.UUID, fabrica_modele: FabricaModele, fals: FurnizorFals
) -> None:
    from app.gateway.rutare import Motiv, motiv_excludere

    fid, _ = furnizor_local(fabrica_modele)
    emb = fabrica_modele.model(fid, identificator="e5", nivel="local", capabilitati=["embeddings"])
    from tests.unit.test_gateway_rutare import cer, profil

    assert (
        motiv_excludere(emb, profil((emb.cod,)), cer(coada="greu"), degradare=False) == Motiv.MODEL_DE_VECTORI
    )


# --- vectorii


@pytest.fixture
def vectori(fabrica_modele: FabricaModele, admin_engine: Engine, fals: FurnizorFals) -> str:
    fid, cod = furnizor_local(fabrica_modele)
    m = fabrica_modele.model(fid, identificator="e5-mic", nivel="local", capabilitati=["embeddings"])
    with admin_engine.begin() as c:
        c.execute(text("UPDATE gateway_modele SET dimensiune_vector = 384 WHERE id = :i"), {"i": m.model_id})
    fals.dim_vectori = 384
    return cod


def test_un_vector_se_calculeaza_cat_timp_toate_culoarele_grele_sunt_ocupate(
    tenant: uuid.UUID, vectori: str, fals: FurnizorFals, porneste_executor: Pornire
) -> None:
    porneste_executor(culoare_greu=2)
    cozi.blocheaza("g1", "g2")
    grele = [motor.trimite(cozi.job, n, coada=Coada.GREU, cheie=f"greu-{n}") for n in ("g1", "g2")]
    cozi.asteapta_pornirea("g1")
    cozi.asteapta_pornirea("g2")  # ambele culoare sunt ocupate
    job = motor.trimite(flux.vectori, str(tenant), coada=Coada.IO, cheie="vectori-io")
    assert motor.asteapta_flux(job, timeout_sec=20).stare is motor.StareJob.TERMINAT
    [v] = flux.VECTORI
    assert len(v) == 2 and all(len(x) == 384 for x in v)
    assert v[0] != v[1]
    # culoarele grele erau în continuare ocupate în tot acest timp
    stari = [motor.stare_flux(j) for j in grele]
    assert all(st is not None and st.stare is motor.StareJob.IN_LUCRU for st in stari)
    assert len(fals.cereri_la(vectori)) == 1
    cozi.elibereaza("g1", "g2")
    for j in grele:
        assert motor.asteapta_flux(j, timeout_sec=20).stare is motor.StareJob.TERMINAT


def test_vectorii_se_verifica_dupa_registru_si_se_noteaza_fara_continut(
    tenant: uuid.UUID, vectori: str, fals: FurnizorFals, admin_engine: Engine
) -> None:
    assert gateway.dimensiune_vectori(tenant) == 384
    v = gateway.vectorizeaza(["text secret al clientului"], tenant_id=tenant)
    assert len(v) == 1 and len(v[0]) == 384
    assert gateway.vectorizeaza(["text secret al clientului"], tenant_id=tenant) == v  # determinist
    with admin_engine.connect() as c:
        rand = c.execute(
            text(
                "SELECT profil, rezultat, motiv_alegere, tokeni_intrare FROM gateway_apeluri WHERE furnizor = :f"
            ),
            {"f": vectori},
        ).first()
        continut = c.execute(
            text(
                "SELECT count(*) FROM gateway_apeluri_continut k JOIN gateway_apeluri a ON a.id = k.apel_id WHERE a.furnizor = :f"
            ),
            {"f": vectori},
        ).scalar_one()
    assert rand is not None and tuple(rand)[:3] == ("vectori", "ok", "1 texte") and rand[3] > 0
    assert continut == 0  # textele clientului nu se păstrează
    fals.dim_vectori = 100  # modelul din server nu mai corespunde registrului
    with pytest.raises(gateway.FurnizoriIndisponibili):
        gateway.vectorizeaza(["alt text"], tenant_id=tenant)


def test_server_de_vectori_cazut_amana_nu_pierde(tenant: uuid.UUID, vectori: str, fals: FurnizorFals) -> None:
    fals.scenariu(vectori, permanent="5xx")
    with pytest.raises(gateway.Amanat) as amanat:
        gateway.vectorizeaza(["x"], tenant_id=tenant)
    assert "vectori" in amanat.value.motiv
    assert len(fals.cereri_la(vectori)) == 4  # o încercare + 3 reîncercări
    fals.scenariu(vectori)  # revine
    with pytest.raises(
        gateway.Amanat
    ):  # întrerupătorul e deschis: nu se mai încearcă până la proba următoare
        gateway.vectorizeaza(["x"], tenant_id=tenant)
    assert len(fals.cereri_la(vectori)) == 4


def test_fara_model_activ_si_cereri_nepermise(tenant: uuid.UUID, fals: FurnizorFals) -> None:
    from app.gateway.vectori import VectoriInvalizi

    with pytest.raises(gateway.Amanat):  # furnizorul `vectori` din sămânță e inactiv
        gateway.vectorizeaza(["x"], tenant_id=tenant)
    assert fals.cereri == []
    for rau in ([], [""], ["   "], ["a"] * 65, ["a" * 20_001]):
        with pytest.raises(VectoriInvalizi):
            gateway.vectorizeaza(rau, tenant_id=tenant)


# --- măsurarea vitezei (server fals pe socket real)


def test_comanda_de_masurare_noteaza_viteza_fiecarui_model_in_registru(
    fabrica_modele: FabricaModele, admin_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    client.seteaza_transport(None)  # socket real spre serverul fals (loopback)
    viteze = {"local-3b": 22.0, "local-7b": 9.5, "local-9b": 6.1}
    with ServerLocalFals(viteze) as server:
        cod = f"loc{uuid.uuid4().hex[:8]}"
        fid = fabrica_modele.furnizor(tip_api="local", cod=cod, url_baza=server.url)
        modele = [
            fabrica_modele.model(fid, identificator=i, nivel="local", capabilitati=["iesire_structurata"])
            for i in (*viteze, "nemontat")  # ultimul nu e servit: 404
        ]
        coduri = [m.cod for m in modele]
        cod_iesire = masurare.main(
            ["--cereri", "3", "--tokeni", "32", *[a for c in coduri for a in ("--model", c)]]
        )
        assert cod_iesire == 0
        mari = [r for r in server.cereri if r["corp"].get("model") == "local-3b"]
        assert len(mari) == 3 and mari[0]["corp"]["temperature"] == 0.0
    iesire = capsys.readouterr().out
    assert "local-3b: 22.0 tokeni/s" in iesire and "local-9b: 6.1 tokeni/s" in iesire
    assert "nemontat: nemăsurat" in iesire
    with admin_engine.connect() as c:
        pe_model = {
            r[0]: (r[1], r[2])
            for r in c.execute(
                text(
                    "SELECT identificator, tokeni_pe_secunda, viteza_masurata_la FROM gateway_modele WHERE furnizor_id = :f"
                ),
                {"f": fid},
            )
        }
    assert float(pe_model["local-3b"][0]) == 22.0 and pe_model["local-3b"][1] is not None
    assert float(pe_model["local-7b"][0]) == 9.5 and float(pe_model["local-9b"][0]) == 6.1
    assert pe_model["nemontat"] == (None, None)  # nimic scris pentru ce n-a putut fi măsurat
    with sesiune_agentie() as db:
        cand = {c.identificator: c for c in registru.candidati(db) if c.furnizor == cod}
    assert cand["local-3b"].tokeni_pe_secunda == 22.0  # registrul o expune rutării / ecranului


def test_adaptorul_local_vorbeste_cu_serverul_pe_http_real() -> None:
    """Contract: cererea structurată și vectorii, pe un socket real (fără transport simulat)."""
    from app.gateway.tipuri import Destinatie

    client.seteaza_transport(None)  # socket real spre serverul fals (loopback)
    with ServerLocalFals({"m": 5.0}, dim=8) as server:
        dest = Destinatie("local", "local", server.url, "m", {}, frozenset({"iesire_structurata"}))
        r = client.apeleaza_structurat(dest, None, (Mesaj("user", "Clasifică."),), Clasificare)
        assert r.obiect.eticheta == "pozitiv" and r.tokeni_iesire == 40  # type: ignore[attr-defined]
        vec, tokeni = client.trimite_vectori(dest, ["a", "b", "c"])
        assert len(vec) == 3 and all(len(v) == 8 for v in vec) and tokeni == 9
        cerere = server.cereri[0]["corp"]
        assert cerere["response_format"]["json_schema"]["schema"]["properties"]["eticheta"]
        with pytest.raises(Exception):  # noqa: B017 - model nemontat: 404 clasificat ca „cerere”
            client.trimite(Destinatie("local", "local", server.url, "altul", {}), None, _cerere())


def _cerere() -> Any:
    from app.gateway.tipuri import CerereModel

    return CerereModel(mesaje=(Mesaj("user", "x"),))


# --- sămânța din migrare


def test_samanta_locala_exista_inactiva_si_cu_dimensiunea_vectorului_in_registru() -> None:
    with sesiune_agentie() as db:
        f = {x.cod: x for x in registru.furnizori(db)}
        modele = {m.identificator: m for m in registru.modele(db)}
    assert (
        f["local"].stare == "inactiv"
        and f["local"].tip_api == "local"
        and f["local"].url_baza.startswith("http://local-llm")
    )
    assert f["local"].antrenare_pe_date is False and f["local"].uz_comercial is None  # licența se confirmă
    assert gateway.cheie_configurata(f["local"])  # serverul intern nu cere cheie
    locale = [m for m in modele.values() if m.furnizor_id == f["local"].id]
    assert len(locale) == 3 and {m.nivel for m in locale} == {"local"}  # trei mărimi de model
    assert modele["multilingual-e5-small"].dimensiune_vector == 384
    assert "embeddings" in modele["multilingual-e5-small"].capabilitati
    # fără licență confirmată nu se activează
    with pytest.raises(gateway.NuSePoateActiva), sesiune_agentie() as db:
        gateway.activeaza(db, f["local"].id, utilizator_id=None)
    assert json.loads(json.dumps(f["local"].parametri))["timeout_sec"] == 600
