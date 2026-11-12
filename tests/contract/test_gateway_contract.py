"""F3.2 — teste de contract ale clientului unificat: același apel de probă pe trei API-uri diferite (chat completions
compatibil OpenAI, Gemini, Anthropic), cu furnizorul FALS în forma reală a fiecărui API. Apelurile reale rămân
„De verificat la migrare” (STARE.md)."""

import logging
from collections.abc import Iterator
from typing import Literal

import pytest

from app.gateway import client
from app.gateway.erori import EroareFurnizor, IesireInvalida
from app.gateway.iesire import Iesire
from app.gateway.tipuri import CerereModel, Destinatie, Mesaj
from tests.furnizor_fals import FurnizorFals

CHEIE = "sk-test-NU-ESTE-O-CHEIE-REALA-0123456789"


class Clasificare(Iesire):
    eticheta: Literal["pozitiv", "negativ", "neutru"]


MESAJE = (Mesaj("system", "Clasifică sentimentul."), Mesaj("user", "Livrarea a fost rapidă, mulțumim!"))
STRUCTURAT = frozenset({"iesire_structurata"})
OPENROUTER = Destinatie(
    "openrouter", "openai_compat", "https://openrouter.ai/api/v1", "openai/gpt-oss-20b:free"
)
GROQ_NATIV = Destinatie(
    "groq", "openai_compat", "https://api.groq.com/openai/v1", "openai/gpt-oss-20b", capabilitati=STRUCTURAT
)
GEMINI = Destinatie(
    "gemini",
    "gemini",
    "https://generativelanguage.googleapis.com/v1beta",
    "gemini-2.5-flash",
    capabilitati=STRUCTURAT,
)
CLAUDE = Destinatie(
    "anthropic", "anthropic", "https://api.anthropic.com", "claude-sonnet-4-5", capabilitati=STRUCTURAT
)
CLOUDFLARE = Destinatie(
    "cloudflare",
    "openai_compat",
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    parametri={"account_id": "acc123"},
)
TOATE = [OPENROUTER, GROQ_NATIV, GEMINI, CLAUDE, CLOUDFLARE]
GAZDE = {
    "openrouter": "openrouter.ai",
    "groq": "api.groq.com",
    "gemini": "generativelanguage.googleapis.com",
    "anthropic": "api.anthropic.com",
    "cloudflare": "api.cloudflare.com",
}


@pytest.fixture
def fals() -> Iterator[FurnizorFals]:
    f = FurnizorFals()
    client.seteaza_transport(f.transport)
    yield f
    client.seteaza_transport(None)


def _ids(d: Destinatie) -> str:
    return d.furnizor


@pytest.mark.parametrize("dest", TOATE, ids=_ids)
def test_acelasi_apel_de_proba_reuseste_pe_fiecare_furnizor(fals: FurnizorFals, dest: Destinatie) -> None:
    r = client.apeleaza_structurat(dest, CHEIE, MESAJE, Clasificare)
    assert isinstance(r.obiect, Clasificare) and r.obiect.eticheta == "pozitiv" and r.obiect.incredere == 0.9
    assert not r.reparat and len(fals.cereri) == 1
    assert r.tokeni_intrare > 0 and r.tokeni_iesire > 0
    assert fals.cereri[0].gazda == GAZDE[dest.furnizor]


def test_cele_trei_api_uri_au_forme_de_cerere_diferite(fals: FurnizorFals) -> None:
    for d in (OPENROUTER, GEMINI, CLAUDE):
        client.apeleaza_structurat(d, CHEIE, MESAJE, Clasificare)
    deschis, gemini, claude = fals.cereri
    assert deschis.cale == "/api/v1/chat/completions" and deschis.antete["authorization"] == f"Bearer {CHEIE}"
    assert gemini.cale == "/v1beta/models/gemini-2.5-flash:generateContent"
    assert (
        gemini.antete["x-goog-api-key"] == CHEIE and "key=" not in gemini.cale
    )  # cheia în antet, nu în adresă
    assert claude.cale == "/v1/messages" and claude.antete["x-api-key"] == CHEIE
    assert claude.antete["anthropic-version"] == "2023-06-01"


def test_forma_cererii_openai_cu_si_fara_schema_nativa(fals: FurnizorFals) -> None:
    client.apeleaza_structurat(GROQ_NATIV, CHEIE, MESAJE, Clasificare)
    client.apeleaza_structurat(OPENROUTER, CHEIE, MESAJE, Clasificare)
    nativ, instructiune = (c.corp for c in fals.cereri)
    assert nativ["response_format"]["type"] == "json_schema"
    assert nativ["response_format"]["json_schema"]["schema"]["properties"]["eticheta"]
    assert nativ["messages"][0] == {"role": "system", "content": "Clasifică sentimentul."}
    assert "response_format" not in instructiune  # modelul fără capabilitate primește schema în instrucțiuni
    assert (
        "eticheta" in instructiune["messages"][0]["content"]
        and "JSON" in instructiune["messages"][0]["content"]
    )
    assert instructiune["max_tokens"] == 1024 and instructiune["model"] == "openai/gpt-oss-20b:free"


def test_forma_cererii_gemini(fals: FurnizorFals) -> None:
    client.apeleaza_structurat(GEMINI, CHEIE, MESAJE, Clasificare)
    corp = fals.cereri[0].corp
    assert corp["systemInstruction"] == {"parts": [{"text": "Clasifică sentimentul."}]}
    assert corp["contents"] == [{"role": "user", "parts": [{"text": "Livrarea a fost rapidă, mulțumim!"}]}]
    cfg = corp["generationConfig"]
    assert (
        cfg["responseMimeType"] == "application/json" and cfg["responseJsonSchema"]["properties"]["eticheta"]
    )
    assert cfg["maxOutputTokens"] == 1024


def test_forma_cererii_anthropic_cu_unealta_fortata(fals: FurnizorFals) -> None:
    client.apeleaza_structurat(CLAUDE, CHEIE, MESAJE, Clasificare)
    corp = fals.cereri[0].corp
    assert corp["system"] == "Clasifică sentimentul."
    assert corp["messages"] == [{"role": "user", "content": "Livrarea a fost rapidă, mulțumim!"}]
    assert corp["tool_choice"] == {"type": "tool", "name": corp["tools"][0]["name"]}
    assert corp["tools"][0]["input_schema"]["properties"]["eticheta"] and corp["max_tokens"] == 1024


def test_adresa_cu_parametri_si_parametru_lipsa(fals: FurnizorFals) -> None:
    client.apeleaza_structurat(CLOUDFLARE, CHEIE, MESAJE, Clasificare)
    assert fals.cereri[0].cale == "/client/v4/accounts/acc123/ai/v1/chat/completions"
    fara = Destinatie("cloudflare", "openai_compat", CLOUDFLARE.url_baza, "m", parametri={"account_id": ""})
    with pytest.raises(EroareFurnizor) as exc:
        client.apeleaza_structurat(fara, CHEIE, MESAJE, Clasificare)
    assert exc.value.fel == "cerere" and len(fals.cereri) == 1  # nu s-a trimis nicio cerere greșită


def test_antetele_de_limita_ajung_in_raspuns(fals: FurnizorFals) -> None:
    r = client.trimite(GROQ_NATIV, CHEIE, CerereModel(mesaje=MESAJE))
    assert (r.antete.limita_cereri, r.antete.ramas_cereri, r.antete.ramas_tokeni) == (1000, 999, 11800)
    assert r.antete.reset_tokeni_la is not None
    r = client.trimite(CLAUDE, CHEIE, CerereModel(mesaje=MESAJE))
    assert (r.antete.ramas_cereri, r.antete.ramas_tokeni) == (49, 39000)
    assert client.trimite(GEMINI, CHEIE, CerereModel(mesaje=MESAJE)).antete.gol  # Gemini nu trimite antete


@pytest.mark.parametrize(
    ("dest", "cuvant", "fel", "status", "retry"),
    [
        (GROQ_NATIV, "429", "limita", 429, 7.0),
        (GEMINI, "429", "limita", 429, 34.0),  # pauza vine din corp (`retryDelay`)
        (CLAUDE, "429", "limita", 429, 12.0),
        (GROQ_NATIV, "5xx", "server", 500, None),
        (GEMINI, "5xx", "server", 503, None),
        (CLAUDE, "5xx", "server", 529, None),
        (GROQ_NATIV, "timeout", "retea", None, None),
        (CLAUDE, "timeout", "retea", None, None),
        (GROQ_NATIV, "401", "autentificare", 401, None),
        (GEMINI, "401", "autentificare", 403, None),
        (CLAUDE, "401", "autentificare", 401, None),
        (GROQ_NATIV, "400", "cerere", 400, None),
        (GEMINI, "continut_blocat", "continut", 200, None),
    ],
    ids=lambda v: v.furnizor if isinstance(v, Destinatie) else str(v),
)
def test_erorile_furnizorilor_se_clasifica_dupa_7_5(
    fals: FurnizorFals, dest: Destinatie, cuvant: str, fel: str, status: int | None, retry: float | None
) -> None:
    fals.scenariu(GAZDE[dest.furnizor], cuvant)
    with pytest.raises(EroareFurnizor) as exc:
        client.apeleaza_structurat(dest, CHEIE, MESAJE, Clasificare)
    assert exc.value.fel == fel and exc.value.status == status and exc.value.retry_dupa == retry
    assert len(fals.cereri) == 1  # clientul nu reîncearcă singur: reîncercările sunt ale gateway-ului


@pytest.mark.parametrize("dest", [OPENROUTER, GEMINI, CLAUDE], ids=_ids)
def test_o_reparatie_dupa_json_stricat_apoi_reuseste(fals: FurnizorFals, dest: Destinatie) -> None:
    gazda = GAZDE[dest.furnizor]
    # Anthropic nu poate întoarce JSON stricat într-o unealtă: acolo textul stricat vine ca bloc de text
    fals.scenariu(gazda, "json_invalid", "ok")
    r = client.apeleaza_structurat(dest, CHEIE, MESAJE, Clasificare)
    assert r.reparat and len(fals.cereri_la(gazda)) == 2
    a_doua = fals.cereri_la(gazda)[1].text_prompt
    assert (
        "JSON invalid" in a_doua and '\\"dovezi\\": [' in a_doua
    )  # răspunsul greșit (în JSON, ghilimele scăpate) și eroarea exactă
    assert r.obiect.incredere == 0.9  # type: ignore[attr-defined]


@pytest.mark.parametrize("dest", [OPENROUTER, GEMINI, CLAUDE], ids=_ids)
def test_dupa_o_singura_reparatie_ieșirea_invalida_ridica_eroare_tipizata(
    fals: FurnizorFals, dest: Destinatie
) -> None:
    gazda = GAZDE[dest.furnizor]
    fals.scenariu(gazda, "schema_gresita", "schema_gresita", "ok")
    with pytest.raises(IesireInvalida) as exc:
        client.apeleaza_structurat(dest, CHEIE, MESAJE, Clasificare)
    assert len(fals.cereri_la(gazda)) == 2  # prima cerere + exact o reparație
    assert "eticheta" in str(exc.value)


@pytest.mark.parametrize("dest", TOATE, ids=_ids)
def test_cheia_nu_apare_in_erori_nici_in_jurnale(
    fals: FurnizorFals, dest: Destinatie, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    gazda = GAZDE[dest.furnizor]
    mesaje_cu_continut = (Mesaj("user", "Ion Popescu, telefon 0722123456"),)
    for cuvant in ("401", "429", "5xx", "timeout", "400"):
        fals.scenariu(gazda, cuvant)
        with pytest.raises(EroareFurnizor) as exc:
            client.apeleaza_structurat(dest, CHEIE, mesaje_cu_continut, Clasificare)
        text = f"{exc.value} {exc.value!r} {exc.value.args}"
        assert CHEIE not in text and gazda not in text and "0722123456" not in text and "Bearer" not in text
    fals.scenariu(gazda, "schema_gresita", "schema_gresita")
    with pytest.raises(IesireInvalida) as exc2:
        client.apeleaza_structurat(dest, CHEIE, mesaje_cu_continut, Clasificare)
    assert CHEIE not in f"{exc2.value!r}"
    jurnal = "\n".join(f"{r.getMessage()} {r.args}" for r in caplog.records)
    assert CHEIE not in jurnal and "0722123456" not in jurnal and gazda not in jurnal
