"""G-pool: catalogul, secretele, rutarea cu familii și sănătate pe model, verificarea furnizorilor (simulat)."""

import datetime as dt
import itertools
import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from app.gateway import catalog, client, sanatate_model, secrete, seif, verifica_furnizori
from app.gateway.erori import EroareFurnizor
from app.gateway.rutare import Motiv, alege, motiv_excludere
from tests.unit.test_gateway_rutare import ACUM, cand, cer, coduri, profil


@pytest.fixture(autouse=True)
def mediu_gol(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Niciun secret din catalog în mediu, seiful gol (fără bază)."""
    for nume in catalog.NUME_SECRETE:
        monkeypatch.delenv(nume, raising=False)
    monkeypatch.delenv("AMA_CHEIE_OPENROUTER", raising=False)
    monkeypatch.setattr(seif, "citeste", lambda _nume: None)
    sanatate_model.reseteaza()
    yield
    sanatate_model.reseteaza()
    client.seteaza_transport(None)


# --- catalogul


def test_catalogul_e_coerent_si_are_numele_exacte_ale_secretelor() -> None:
    assert catalog.valideaza() == []
    assert catalog.PROVIDER_SECRETS["cloudflare"] == ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")
    assert catalog.PROVIDER_SECRETS["nvidia_nim"] == ("NVIDIA_NIM_API_KEY", "NVIDIA_NIM_BASE_URL")
    assert catalog.PROVIDER_SECRETS["gemini"] == ("GEMINI_API_KEY",)
    assert catalog.PROVIDER_SECRETS["openrouter"] == ("OPENROUTER_API_KEY",)
    assert "kilo" in catalog.OPENAI_COMPATIBLE and "openrouter" not in catalog.OPENAI_COMPATIBLE
    assert all(f.tip_api in ("openai_compat", "gemini") for f in catalog.FURNIZORI_POOL)


def test_familia_vine_din_catalog_sau_din_identificator() -> None:
    assert catalog.familie("groq/openai/gpt-oss-120b") == catalog.Familie.GPT_OSS
    assert catalog.familie("groq/llama-3.3-70b-versatile") == catalog.Familie.LLAMA
    assert catalog.familie("anthropic/claude-sonnet-4-5") == catalog.Familie.CLAUDE
    assert catalog.familie("x/necunoscut") == ""


def test_rezervele_unui_rol_alterneaza_familiile_si_respecta_nivelul() -> None:
    for rol, nivel in catalog.ROLURI.items():
        lant = catalog.rezerva_rol(rol)
        assert lant and len(lant) <= catalog.REZERVE_MAXIM
        assert all(catalog.RANG_NIVEL[catalog.MODELE[k].nivel] >= catalog.RANG_NIVEL[nivel] for k in lant)
        familii = [catalog.familie(k) for k in lant]
        # primele modele vin din familii diferite două câte două
        assert all(a != b for a, b in itertools.pairwise(familii[:6])), rol
    assert catalog.rezerva_rol("consiliu") == ()
    lente = [k for k in catalog.rezerva_rol("strategie") if catalog.MODELE[k].lent]
    rapide = [k for k in catalog.rezerva_rol("strategie") if not catalog.MODELE[k].lent]
    assert list(catalog.rezerva_rol("strategie")) == rapide + lente


def test_alternarea_e_stabila_cand_nu_exista_alta_familie() -> None:
    lant = ["groq/openai/gpt-oss-120b", "groq/openai/gpt-oss-20b", "groq/qwen/qwen3.8-27b"]
    assert catalog.alterneaza_familii(lant) == [lant[0], lant[2], lant[1]]
    assert catalog.alterneaza_familii(lant[:2]) == lant[:2]


def test_resetul_gemini_e_miezul_noptii_la_los_angeles_cu_ora_de_vara() -> None:
    vara = dt.datetime(2026, 7, 1, 12, tzinfo=dt.UTC)
    iarna = dt.datetime(2026, 12, 1, 12, tzinfo=dt.UTC)
    assert catalog.ora_reset_utc(catalog.LOS_ANGELES, vara) == 7
    assert catalog.ora_reset_utc(catalog.LOS_ANGELES, iarna) == 8
    assert catalog.ora_reset_utc("UTC", iarna) == 0


# --- secretele


def test_furnizor_fara_toate_secretele_e_dezactivat(monkeypatch: pytest.MonkeyPatch) -> None:
    assert secrete.lipsa("cloudflare") == ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"]
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "simulat")
    assert secrete.lipsa("cloudflare") == ["CLOUDFLARE_ACCOUNT_ID"]
    assert not secrete.complet("cloudflare")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "cont-simulat")
    assert secrete.complet("cloudflare")
    assert secrete.cheie("cloudflare") == "simulat"


def test_numele_vechi_al_cheii_ramane_valabil_pentru_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    assert not secrete.complet("openrouter", "AMA_CHEIE_OPENROUTER")
    monkeypatch.setenv("AMA_CHEIE_OPENROUTER", "veche")
    assert secrete.cheie("openrouter", "AMA_CHEIE_OPENROUTER") == "veche"
    monkeypatch.setenv("OPENROUTER_API_KEY", "noua")
    assert secrete.cheie("openrouter", "AMA_CHEIE_OPENROUTER") == "noua"  # numele exact are întâietate


def test_doar_numele_din_catalog_se_citesc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMA_MASTER_KEY", "nu-se-citeste-" + "x" * 30)
    assert secrete.citeste("AMA_MASTER_KEY") is None
    assert secrete.citeste_cheie_env("AMA_DATABASE_URL") is None


def test_seiful_e_rezerva_dupa_mediu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seif, "citeste", lambda n: "din-seif" if n == "GROQ_API_KEY" else None)
    assert secrete.cheie("groq") == "din-seif"
    monkeypatch.setenv("GROQ_API_KEY", "din-mediu")
    assert secrete.cheie("groq") == "din-mediu"


def test_completeaza_parametrii_si_adresa_din_secrete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "cont1")
    c = secrete.completeaza(cand("cloudflare", parametri={"account_id": ""}))
    assert c.parametri["account_id"] == "cont1"
    monkeypatch.setenv("NVIDIA_NIM_BASE_URL", "https://nim.exemplu.test/v1")
    assert secrete.completeaza(cand("nvidia_nim")).url_baza == "https://nim.exemplu.test/v1"
    monkeypatch.setenv("NVIDIA_NIM_BASE_URL", "http://nesigur.test")
    assert secrete.completeaza(cand("nvidia_nim")).url_baza == "https://exemplu.test"  # doar https


# --- rutarea


def test_judecatorul_din_alta_familie_decat_autorul() -> None:
    a = cand("groq", "llama-70b", familie="Meta Llama")
    b = cand("cloudflare", "llama-cf", familie="Meta Llama")
    c = cand("groq", "qwen", familie="Alibaba Qwen")
    sel = alege(
        profil((a.cod, b.cod, c.cod)), [a, b, c], cer(alt_model_decat=a.cod, familie_autor="Meta Llama")
    )
    assert coduri(sel.principal) == [c.cod]
    assert (b.cod, Motiv.ACEEASI_FAMILIE) in sel.excluse


def test_modelul_bolnav_si_cererea_prea_mare_pentru_context_cad() -> None:
    a, b = cand(ident="mic", context_tokeni=1000), cand(ident="bun", context_tokeni=100_000)
    p = profil((a.cod, b.cod))
    assert motiv_excludere(a, p, cer(tokeni_estimati=5000), degradare=False) == Motiv.CONTEXT_MIC
    assert motiv_excludere(b, p, cer(modele_indisponibile=frozenset({b.cod})), degradare=False) == (
        Motiv.MODEL_INDISPONIBIL
    )
    assert coduri(alege(p, [a, b], cer(tokeni_estimati=5000)).principal) == [b.cod]


def test_rezerva_rolului_se_expandeaza_si_rezervele_nepotrivite_se_sar_in_tacere() -> None:
    k1, k2 = catalog.rezerva_rol("judecata")[:2]
    f1, m1 = k1.split("/", 1)
    f2, m2 = k2.split("/", 1)
    explicit = cand("a", "explicit")
    r1 = cand(f1, m1, familie=catalog.familie(k1))
    r2 = cand(f2, m2, familie=catalog.familie(k2), stare_furnizor="inactiv")
    sel = alege(profil((explicit.cod, "rezerva:judecata")), [r2, r1, explicit], cer())
    assert coduri(sel.principal) == [explicit.cod, r1.cod]
    assert sel.excluse == ()  # r2 (furnizor inactiv) nu strică diagnosticul lanțului explicit


# --- sănătatea pe model


def test_404_scoate_modelul_o_zi_iar_erorile_repetate_cateva_minute() -> None:
    assert sanatate_model.esec("a/m", EroareFurnizor("cerere", status=404), acum=ACUM) is not None
    assert "a/m" in sanatate_model.indisponibile(ACUM + dt.timedelta(hours=23))
    assert "a/m" not in sanatate_model.indisponibile(ACUM + dt.timedelta(hours=25))
    for _ in range(sanatate_model.PRAG_ERORI - 1):
        assert sanatate_model.esec("b/m", EroareFurnizor("server", status=503), acum=ACUM) is None
    assert sanatate_model.esec("b/m", EroareFurnizor("retea"), acum=ACUM) is not None
    assert "b/m" in sanatate_model.indisponibile(ACUM)
    sanatate_model.succes("b/m")
    assert "b/m" not in sanatate_model.indisponibile(ACUM)
    assert sanatate_model.esec("c/m", EroareFurnizor("limita", status=429), acum=ACUM) is None


# --- verificarea furnizorilor, pe transport HTTP simulat


def _transport(cereri: list[httpx.Request], *, esec_la: str = "") -> httpx.MockTransport:
    def raspunde(r: httpx.Request) -> httpx.Response:
        cereri.append(r)
        if esec_la and esec_la in r.url.host:
            return httpx.Response(503, json={"error": {"code": "unavailable"}})
        if "generativelanguage" in r.url.host:
            return httpx.Response(
                200,
                json={
                    "candidates": [{"content": {"parts": [{"text": "OK"}]}, "finishReason": "STOP"}],
                    "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 1},
                },
            )
        corp: dict[str, Any] = {
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 1},
        }
        return httpx.Response(200, json=corp)

    return httpx.MockTransport(raspunde)


def test_verificarea_apeleaza_doar_furnizorii_activi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "simulat-groq")
    monkeypatch.setenv("GEMINI_API_KEY", "simulat-gemini")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "simulat-cf")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "cont9")
    cereri: list[httpx.Request] = []
    client.seteaza_transport(_transport(cereri, esec_la="cloudflare"))
    rezultate = {r.furnizor: r for r in verifica_furnizori.verifica()}
    assert rezultate["groq"].stare == "ok" and rezultate["gemini"].stare == "ok"
    assert rezultate["cloudflare"].stare == "eroare" and "503" in rezultate["cloudflare"].detaliu
    assert rezultate["mistral"].stare == "dezactivat" and "MISTRAL_API_KEY" in rezultate["mistral"].detaliu
    assert rezultate["ollama"].stare == "dezactivat"
    assert len(cereri) == 3  # câte un apel mic, doar la cei activi
    cf = next(r for r in cereri if "cloudflare" in r.url.host)
    assert "/accounts/cont9/ai/v1/chat/completions" in str(cf.url)
    assert cf.headers["authorization"] == "Bearer simulat-cf"
    assert json.loads(next(r for r in cereri if "groq" in r.url.host).content)["max_tokens"] == 16
    assert verifica_furnizori.cod_iesire(list(rezultate.values())) == 1


def test_verificarea_fara_furnizori_activi_iese_cu_2_si_nu_arata_chei(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client.seteaza_transport(_transport([]))
    assert verifica_furnizori.main([]) == 2
    monkeypatch.setenv("GROQ_API_KEY", "valoare-secreta-simulata")
    assert verifica_furnizori.main(["--furnizor", "groq", "--toate-modelele"]) == 0
    iesire = capsys.readouterr().out
    assert "valoare-secreta-simulata" not in iesire
    assert iesire.count("groq ") >= len([m for m in catalog.MODELE_POOL if m.furnizor == "groq"])
