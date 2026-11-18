"""Catalogul „pool” de furnizori și modele gratuite (G-pool), portat din catalogul fabricii și adaptat la AMA.

Ce aduce peste registrul din bază (`inventar.py`, F3.1):
- `PROVIDER_SECRETS`: numele EXACTE ale secretelor fiecărui furnizor (din mediu sau din seif,
  `secrete.py`). Un furnizor fără toate secretele e dezactivat automat (motivul `fara_cheie` la rutare);
- `OPENAI_COMPATIBLE`: adresele de bază ale furnizorilor compatibili OpenAI (un singur adaptor,
  `openai_compat`);
- familiile de modele: rutarea alternează familiile în rezerve și poate cere „altă familie decât autorul”;
- fusul orar al resetării zilnice (Gemini: miezul nopții la Los Angeles, nu o oră UTC fixă);
- rezervele pe rol (`rezerva:<profil>` în lanțul unui profil AMA), cu familiile alternate.

Rândurile din bază se seamănă din acest catalog (migrarea `0109`); tot ce e aici sunt DATE, fără secrete.
Limitele sunt valorile cunoscute ale cotelor gratuite la data fabricii (marcaj `I` în bază): limitatorul le
corectează din antetele observate.
# NEVERIFICAT: identificatorii și limitele nu au fost confirmați live din AMA (primul test:
`python -m app.gateway.verifica_furnizori`).
"""

import datetime as dt
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from app.gateway.candidat import RANG_NIVEL


class Familie(StrEnum):
    GEMINI = "Google Gemini"
    GEMMA = "Google Gemma"
    GLM = "Zhipu GLM"
    DEEPSEEK = "DeepSeek"
    NEMOTRON = "NVIDIA Nemotron"
    GPT_OSS = "OpenAI gpt-oss"
    QWEN = "Alibaba Qwen"
    MINIMAX = "MiniMax"
    LLAMA = "Meta Llama"
    MISTRAL = "Mistral"
    POOLSIDE = "Poolside Laguna"
    COHERE = "Cohere"
    CLAUDE = "Anthropic Claude"
    NEDECLARAT = "Model nedeclarat (agregator)"


@dataclass(frozen=True)
class FurnizorPool:
    cod: str
    nume: str
    tip_api: str
    url_baza: str
    secrete: tuple[str, ...]  # primul = cheia de API (antetul); restul completează adresa
    parametri_din: dict[str, str] = field(default_factory=dict)  # nume de secret → parametru din adresă
    url_din: str | None = None  # numele secretului care, dacă e setat (https), înlocuiește adresa de bază
    reset_fus: str = "UTC"  # fusul orar în care se resetează cotele zilnice (la miezul nopții)
    cereri_minut: int | None = None  # limite comune contului
    cereri_zi: int | None = None
    note: str = ""
    sursa: str = ""


LOS_ANGELES = "America/Los_Angeles"

FURNIZORI_POOL: tuple[FurnizorPool, ...] = (
    FurnizorPool(
        "gemini",
        "Google Gemini (nivel gratuit)",
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta",
        ("GEMINI_API_KEY",),
        reset_fus=LOS_ANGELES,
    ),
    FurnizorPool(
        "nvidia_nim",
        "NVIDIA NIM",
        "openai_compat",
        "https://integrate.api.nvidia.com/v1",
        ("NVIDIA_NIM_API_KEY", "NVIDIA_NIM_BASE_URL"),
        url_din="NVIDIA_NIM_BASE_URL",
        sursa="https://build.nvidia.com",
    ),
    FurnizorPool(
        "nvidia_nim_b",
        "NVIDIA NIM (al doilea cont)",
        "openai_compat",
        "https://integrate.api.nvidia.com/v1",
        ("NVIDIA_NIM_API_KEY_B",),
        note="Al doilea cont NVIDIA: altă cotă, aceleași modele.",
        sursa="https://build.nvidia.com",
    ),
    FurnizorPool("groq", "Groq", "openai_compat", "https://api.groq.com/openai/v1", ("GROQ_API_KEY",)),
    FurnizorPool(
        "openrouter",
        "OpenRouter (modele gratuite)",
        "openai_compat",
        "https://openrouter.ai/api/v1",
        ("OPENROUTER_API_KEY",),
    ),
    FurnizorPool(
        "sambanova",
        "SambaNova Cloud",
        "openai_compat",
        "https://api.sambanova.ai/v1",
        ("SAMBANOVA_API_KEY",),
        sursa="https://cloud.sambanova.ai",
    ),
    FurnizorPool(
        "cloudflare",
        "Cloudflare Workers AI",
        "openai_compat",
        "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
        ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"),
        parametri_din={"CLOUDFLARE_ACCOUNT_ID": "account_id"},
    ),
    FurnizorPool(
        "mistral",
        "Mistral La Plateforme (plan gratuit)",
        "openai_compat",
        "https://api.mistral.ai/v1",
        ("MISTRAL_API_KEY",),
        sursa="https://docs.mistral.ai",
    ),
    FurnizorPool(
        "kilo",
        "Kilo Gateway (modele :free)",
        "openai_compat",
        "https://api.kilo.ai/api/openrouter",
        ("KILO_API_KEY",),
        sursa="https://kilo.ai",
    ),
    FurnizorPool(
        "llm7",
        "LLM7 (nivel gratuit)",
        "openai_compat",
        "https://api.llm7.io/v1",
        ("LLM7_API_KEY",),
        sursa="https://llm7.io",
    ),
    FurnizorPool(
        "zai",
        "Z.ai (GLM Flash gratuite)",
        "openai_compat",
        "https://api.z.ai/api/paas/v4",
        ("ZAI_API_KEY",),
        note="Planul gratuit are o singură cerere simultană.",
        sursa="https://z.ai",
    ),
    FurnizorPool(
        "ollama",
        "Ollama Cloud",
        "openai_compat",
        "https://ollama.com/v1",
        ("OLLAMA_API_KEY",),
        note="Fără nivel gratuit pe cont (402): niciun model în rutare până la un plan.",
        sursa="https://ollama.com",
    ),
    FurnizorPool(
        "sealion",
        "SEA-LION (AI Singapore)",
        "openai_compat",
        "https://api.sea-lion.ai/v1",
        ("SEALION_API_KEY",),
        cereri_minut=10,
        note="10 cereri pe minut pe cont, pentru toate modelele.",
        sursa="https://sea-lion.ai",
    ),
)

POOL: dict[str, FurnizorPool] = {f.cod: f for f in FURNIZORI_POOL}
# Cheile (din mediu sau seif) necesare fiecărui furnizor; cei fără toate cheile sunt dezactivați automat.
PROVIDER_SECRETS: dict[str, tuple[str, ...]] = {f.cod: f.secrete for f in FURNIZORI_POOL}
# Furnizorii compatibili OpenAI care nu existau în registrul F3.1, cu adresa lor de bază.
OPENAI_COMPATIBLE: dict[str, str] = {
    f.cod: f.url_baza
    for f in FURNIZORI_POOL
    if f.tip_api == "openai_compat" and f.cod not in ("groq", "openrouter", "cloudflare")
}
NUME_SECRETE: frozenset[str] = frozenset(n for s in PROVIDER_SECRETS.values() for n in s)


@dataclass(frozen=True)
class ModelPool:
    furnizor: str
    model: str
    familie: Familie
    nivel: str  # T1 mic și rapid, T2 mediu, T3 mare
    rpm: int | None = None
    rpd: int | None = None
    tpm: int | None = None
    tpd: int | None = None
    viziune: bool = False
    lent: bool = False  # zeci de secunde pe apel: doar rezervă
    context: int = 128_000

    @property
    def cod(self) -> str:
        return f"{self.furnizor}/{self.model}"

    @property
    def capabilitati(self) -> tuple[str, ...]:
        return ("viziune",) if self.viziune else ()


def _gemini(model: str, nivel: str, *, rpm: int = 10, rpd: int = 250, lent: bool = False) -> ModelPool:
    return ModelPool("gemini", model, Familie.GEMINI, nivel, rpm, rpd, 250_000, viziune=True, lent=lent,
                     context=1_048_576)  # fmt: skip


_NIM: tuple[tuple[str, Familie, str, bool, bool], ...] = (  # (model, familie, nivel, viziune, lent)
    ("nvidia/nemotron-3-ultra-550b-a55b", Familie.NEMOTRON, "T3", False, False),
    ("nvidia/nemotron-3.5-lightning-30b-a3b", Familie.NEMOTRON, "T2", False, False),
    ("mistralai/mistral-large-4-1t-a52b", Familie.MISTRAL, "T3", False, False),
    ("poolside/laguna-xs-2.1", Familie.POOLSIDE, "T1", False, False),
    ("nvidia/nemotron-3.5-super-vl-120b-a12b", Familie.NEMOTRON, "T3", True, False),
    ("z-ai/glm-5.3-flash", Familie.GLM, "T2", False, True),
    ("deepseek-ai/deepseek-v4.1-flash", Familie.DEEPSEEK, "T2", False, True),
    ("minimaxai/minimax-m3.1-flash", Familie.MINIMAX, "T2", False, True),
)


def _cf(model: str, familie: Familie, nivel: str, *, context: int = 128_000) -> ModelPool:
    return ModelPool("cloudflare", model, familie, nivel, rpm=300, context=context)


# Ordinea contează: în cadrul unui nivel, rezervele urmează ordinea de aici (rapide și fiabile întâi, după
# măsurătorile fabricii), apoi familiile se alternează.
MODELE_POOL: tuple[ModelPool, ...] = (
    ModelPool("groq", "qwen/qwen3.8-27b", Familie.QWEN, "T2", 30, 1000, 6000, 200_000),
    ModelPool("groq", "openai/gpt-oss-120b", Familie.GPT_OSS, "T3", 30, 1000, 8000, 200_000),
    ModelPool("groq", "openai/gpt-oss-20b", Familie.GPT_OSS, "T2", 30, 1000, 8000, 200_000),
    _gemini("gemini-3.5-flash-lite", "T1", rpm=15, rpd=1000),
    _gemini("gemini-3.6-flash", "T3"),
    _gemini("gemini-3.5-flash", "T2"),
    _gemini("gemini-3.8-flash", "T3", lent=True),
    ModelPool("mistral", "codestral-latest", Familie.MISTRAL, "T2", 60, None, 500_000),
    ModelPool("mistral", "ministral-14b-2512", Familie.MISTRAL, "T2", 25, None, 900_000),
    _cf("@cf/openai/gpt-oss-120b", Familie.GPT_OSS, "T3"),
    _cf("@cf/qwen/qwen3.8-27b", Familie.QWEN, "T2"),
    _cf("@cf/google/gemma-4-26b-a4b-it", Familie.GEMMA, "T2"),
    _cf("@cf/nvidia/nemotron-3-120b-a12b", Familie.NEMOTRON, "T3"),
    _cf("@cf/mistralai/mistral-small-3.1-24b-instruct", Familie.MISTRAL, "T2"),
    _cf("@cf/meta/llama-3.3-70b-instruct-fp8-fast", Familie.LLAMA, "T2", context=24_000),
    *(
        ModelPool(f, m, fam, niv, rpm=40, viziune=viz, lent=lent)
        for f in ("nvidia_nim", "nvidia_nim_b")
        for m, fam, niv, viz, lent in _NIM
    ),
    ModelPool("nvidia_nim", "z-ai/glm-5.3", Familie.GLM, "T3", rpm=40, lent=True),
    ModelPool("openrouter", "google/gemma-4-31b-it:free", Familie.GEMMA, "T2", 20, 50),
    ModelPool("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", Familie.NEMOTRON, "T3", 20, 50),
    ModelPool("kilo", "poolside/laguna-s-2.1:free", Familie.POOLSIDE, "T2", 20),
    ModelPool("kilo", "nvidia/nemotron-3.5-super-vl:free", Familie.NEMOTRON, "T3", 20, viziune=True),
    ModelPool("kilo", "cohere/north-mini-code:free", Familie.COHERE, "T1", 20),
    ModelPool("kilo", "kilo-auto/free", Familie.NEDECLARAT, "T2", 20),
    ModelPool("llm7", "fast", Familie.NEDECLARAT, "T1", 20),
    ModelPool("llm7", "codestral-latest", Familie.MISTRAL, "T2", 10),
    ModelPool("sealion", "aisingapore/Nemotron-SEA-LION-v4.8-120B-A12B", Familie.NEMOTRON, "T3", 3),
    ModelPool("sealion", "aisingapore/Llama-SEA-LION-v3-70B-IT", Familie.LLAMA, "T2", 3),
    ModelPool("sealion", "aisingapore/Qwen-SEA-LION-v4-32B-IT", Familie.QWEN, "T2", 2),  # pragma: allowlist secret
    ModelPool("sealion", "aisingapore/Gemma-SEA-LION-v4-27B-IT", Familie.GEMMA, "T2", 2),
    ModelPool("sambanova", "Meta-Llama-3.3-70B-Instruct", Familie.LLAMA, "T2", 20, 20),
    ModelPool("zai", "glm-4.5-flash", Familie.GLM, "T2", 10),
    ModelPool("zai", "glm-4.7-flash", Familie.GLM, "T2", 10, lent=True),
)
MODELE: dict[str, ModelPool] = {m.cod: m for m in MODELE_POOL}

# Familia modelelor care nu sunt în catalog (registrul F3.1), după identificator.
_FAMILII_DIN_NUME: tuple[tuple[re.Pattern[str], Familie], ...] = tuple(
    (re.compile(p, re.IGNORECASE), f)
    for p, f in (
        (r"gemini", Familie.GEMINI), (r"gemma", Familie.GEMMA), (r"claude", Familie.CLAUDE),
        (r"gpt-oss", Familie.GPT_OSS), (r"llama", Familie.LLAMA), (r"qwen", Familie.QWEN),
        (r"mistral|codestral|ministral|devstral", Familie.MISTRAL), (r"nemotron", Familie.NEMOTRON),
        (r"deepseek", Familie.DEEPSEEK), (r"glm", Familie.GLM), (r"minimax", Familie.MINIMAX),
        (r"laguna|poolside", Familie.POOLSIDE), (r"cohere|command", Familie.COHERE),
    )
)  # fmt: skip


def familie(cod_model: str) -> str:
    """Familia unui model (`furnizor/identificator`); șir gol dacă nu se recunoaște (o familie proprie)."""
    m = MODELE.get(cod_model)
    if m is not None:
        return m.familie.value
    for tipar, fam in _FAMILII_DIN_NUME:
        if tipar.search(cod_model.split("/", 1)[-1]):
            return fam.value
    return ""


def ora_reset_utc(fus: str, acum: dt.datetime) -> int:
    """Ora UTC la care cade miezul nopții în fusul `fus`, în ziua lui `acum` (ține cont de ora de vară)."""
    local = acum.astimezone(ZoneInfo(fus))
    miezul_noptii = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return miezul_noptii.astimezone(dt.UTC).hour


def alterneaza_familii(coduri: list[str]) -> list[str]:
    """Reordonare stabilă: la fiecare pas, primul model rămas dintr-o familie diferită de cea de dinainte
    (dacă există). O furtună de erori într-o familie sau la un furnizor nu ține pe loc tot lanțul."""
    ramase = list(coduri)
    rezultat: list[str] = []
    while ramase:
        anterior = familie(rezultat[-1]) if rezultat else None
        alege = next((c for c in ramase if not anterior or familie(c) != anterior), ramase[0])
        ramase.remove(alege)
        rezultat.append(alege)
    return rezultat


# Rolurile AMA (profilurile de sarcină, `profiluri.py`) și nivelul minim al rezervelor lor.
ROLURI: dict[str, str] = {
    "clasificare": "T1",
    "rescriere": "T2",
    "creatie": "T2",
    "judecata": "T2",
    "strategie": "T3",
}
REZERVE_MAXIM = 24


def rezerva_rol(rol: str) -> tuple[str, ...]:
    """Rezervele unui rol: modelele de nivel cel puțin cel al rolului, cele rapide înaintea celor lente,
    cu familiile alternate. Rolurile mici încep cu modelele mici (rapide, cote mari)."""
    nivel = ROLURI.get(rol)
    if nivel is None:
        return ()
    minim = RANG_NIVEL[nivel]
    eligibile = [m for m in MODELE_POOL if RANG_NIVEL[m.nivel] >= minim]
    ordonate = sorted(
        enumerate(eligibile), key=lambda p: (p[1].lent, abs(RANG_NIVEL[p[1].nivel] - minim), p[0])
    )
    rapide = alterneaza_familii([m.cod for _, m in ordonate if not m.lent])
    lente = alterneaza_familii([m.cod for _, m in ordonate if m.lent])
    return tuple((rapide + lente)[:REZERVE_MAXIM])


def descriere_seed(m: ModelPool) -> dict[str, Any]:
    """Valorile unui rând `gateway_modele` pentru sămânță (fără secrete)."""
    return {
        "furnizor": m.furnizor,
        "identificator": m.model,
        "nume_afisat": m.model.split("/")[-1][:120],
        "nivel": m.nivel,
        "context_tokeni": m.context,
        "capabilitati": list(m.capabilitati),
        "cereri_minut": m.rpm,
        "cereri_zi": m.rpd,
        "tokeni_minut": m.tpm,
        "tokeni_zi": m.tpd,
        "note": f"Familie: {m.familie.value}." + (" Lent: doar rezervă." if m.lent else ""),
    }


def valideaza() -> list[str]:
    probleme: list[str] = []
    for f in FURNIZORI_POOL:
        if not f.secrete:
            probleme.append(f"{f.cod}: fără secrete declarate")
        if not f.url_baza.startswith("https://"):
            probleme.append(f"{f.cod}: adresa de bază trebuie să fie https")
        for s in (*f.parametri_din, *(x for x in (f.url_din,) if x)):
            if s not in f.secrete:
                probleme.append(f"{f.cod}: {s} nu e printre secretele furnizorului")
        try:
            ZoneInfo(f.reset_fus)
        except (KeyError, ValueError):
            probleme.append(f"{f.cod}: fus orar necunoscut {f.reset_fus!r}")
    for s in NUME_SECRETE:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,60}", s):
            probleme.append(f"nume de secret nepermis: {s!r}")
    for m in MODELE_POOL:
        if m.furnizor not in POOL:
            probleme.append(f"{m.cod}: furnizor necunoscut")
        if m.nivel not in ("T1", "T2", "T3"):
            probleme.append(f"{m.cod}: nivel nepermis în pool {m.nivel!r}")
    if len(MODELE) != len(MODELE_POOL):
        probleme.append("model dublat în catalog")
    return probleme
