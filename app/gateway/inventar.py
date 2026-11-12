"""Inventarul de pornire al furnizorilor și modelelor, ca DATE (nu ca `if`-uri). Sursa: `docs/02` §2.2 (fapte
verificate la 2026-11-10) și ce se știe despre API-urile lor.

Marcajele păstrează încrederea fiecărui fapt, ca în documentație: `V` = verificat la sursă (cu data), `S` =
din
sursă secundară, `I` = presupunere de proiectare, NEVERIFICATĂ (fără dată de verificare). Tot ce e `I` se
confirmă la completarea inventarului proprietarului (F0.3, `docs/registre/inventar-modele.md`, încă
necompletat)
și la migrarea pe VPS. Identificatorii modelelor sunt exemple plauzibile: furnizorii îi schimbă des.

Toți furnizorii pornesc `inactiv`: proprietarul îi activează după ce a pus cheia în mediu. Cheile NU sunt
aici și
nu sunt în bază: `cheie_env` este doar NUMELE variabilei de mediu din care se citește cheia (decizia F3.1).
"""

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

TIPURI_API = ("openai_compat", "gemini", "anthropic")  # cele implementate în F3.2; "local" vine cu F3.5
NIVELURI = ("T1", "T2", "T3", "T4", "local")
CAPABILITATI = ("iesire_structurata", "unelte", "viziune")
MARCAJE = ("V", "S", "I")
FERESTRE = ("minut", "zi")
NUME_VARIABILA = re.compile(r"^AMA_CHEIE_[A-Z0-9_]{1,40}$")
COD = re.compile(r"^[a-z][a-z0-9_]{1,30}$")

VERIFICAT = dt.date(2026, 11, 10)  # data faptelor din docs/02 §2.2


@dataclass(frozen=True)
class Limite:
    cereri_minut: int | None = None
    cereri_zi: int | None = None
    tokeni_minut: int | None = None
    tokeni_zi: int | None = None


@dataclass(frozen=True)
class FurnizorSeed:
    cod: str
    nume: str
    tip_api: str
    url_baza: str
    cheie_env: str
    platit: bool  # apelurile lui costă bani reali (oprirea „apeluri plătite” îl scoate din lanț)
    uz_comercial: bool | None  # None = necunoscut: nu se poate activa
    antrenare_pe_date: bool | None  # None = necunoscut: nu primește date confidențiale
    restrictii_regionale: str
    note: str
    marcaj: str  # încrederea în termeni (uz comercial, antrenare, regiuni)
    verificat_la: dt.date | None
    sursa: str
    limite: Limite = field(
        default_factory=Limite
    )  # limite comune întregului cont, dacă furnizorul le aplică așa
    reset_zi_ora: int = 0  # ora UTC la care se resetează limitele zilnice
    parametri: dict[str, Any] = field(default_factory=dict)  # fără secrete


@dataclass(frozen=True)
class ModelSeed:
    furnizor: str
    identificator: str
    nume_afisat: str
    nivel: str
    context_tokeni: int
    capabilitati: tuple[str, ...]
    limite: Limite
    pret_umbra_intrare: float  # USD la 1 milion de tokeni, cât ar costa la un furnizor plătit (8.5)
    pret_umbra_iesire: float
    marcaj: str  # încrederea în limite
    verificat_la: dt.date | None
    sursa: str
    note: str = ""


FURNIZORI: tuple[FurnizorSeed, ...] = (
    FurnizorSeed(
        cod="openrouter",
        nume="OpenRouter (modele gratuite)",
        tip_api="openai_compat",
        url_baza="https://openrouter.ai/api/v1",
        cheie_env="AMA_CHEIE_OPENROUTER",
        platit=False,
        uz_comercial=True,
        antrenare_pe_date=None,
        restrictii_regionale="",
        note="Termenii diferă de la un model gratuit la altul (unele păstrează și folosesc promptul): se "
        "confirmă "
        "pe fiecare model înainte să primească date de client. Limita este pe cont, nu pe model; după o "
        "cumpărare unică de 10 USD limita zilnică urcă de la 50 la 1.000 de cereri.",
        marcaj="I",
        verificat_la=None,
        sursa="https://openrouter.ai/docs/limits",
        limite=Limite(cereri_minut=20, cereri_zi=50),
        parametri={"antete_cheie": "furnizor"},  # limita e pe cont: antetele corectează contorul contului
    ),
    FurnizorSeed(
        cod="groq",
        nume="Groq",
        tip_api="openai_compat",
        url_baza="https://api.groq.com/openai/v1",
        cheie_env="AMA_CHEIE_GROQ",
        platit=False,
        uz_comercial=True,
        antrenare_pe_date=None,
        restrictii_regionale="",
        note="Limitele se aplică la nivel de organizație, pe model. Antetele de limită: cererile sunt pe zi, "
        "tokenii pe minut.",
        marcaj="I",
        verificat_la=None,
        sursa="https://console.groq.com/docs/rate-limits",
        parametri={"antete_cereri": "zi", "antete_tokeni": "minut"},
    ),
    FurnizorSeed(
        cod="gemini",
        nume="Google Gemini (nivel gratuit)",
        tip_api="gemini",
        url_baza="https://generativelanguage.googleapis.com/v1beta",
        cheie_env="AMA_CHEIE_GEMINI",
        platit=False,
        uz_comercial=False,
        antrenare_pe_date=True,
        restrictii_regionale="Din 23 martie 2026, aplicațiile oferite utilizatorilor din SEE pot folosi doar "
        "serviciile plătite.",
        note="Nivelul gratuit NU intră în calea de producție pentru clienți (docs/02 §2.2). Rămâne în "
        "registru "
        "pentru teste și pentru o eventuală trecere pe nivelul plătit.",
        marcaj="V",
        verificat_la=VERIFICAT,
        sursa="https://ai.google.dev/gemini-api/terms",
    ),
    FurnizorSeed(
        cod="cloudflare",
        nume="Cloudflare Workers AI",
        tip_api="openai_compat",
        url_baza="https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
        cheie_env="AMA_CHEIE_CLOUDFLARE",
        platit=False,
        uz_comercial=True,
        antrenare_pe_date=None,
        restrictii_regionale="",
        note="Cota este de 10.000 de „neuroni” pe zi, comună cu imaginile: nu se exprimă în tokeni, deci "
        "nu are "
        "limite numerice aici (se măsoară în F3.6). Cere `account_id` în parametri.",
        marcaj="S",
        verificat_la=VERIFICAT,
        sursa="https://developers.cloudflare.com/workers-ai/platform/pricing/",
        parametri={"account_id": ""},
    ),
    FurnizorSeed(
        cod="anthropic",
        nume="Anthropic Claude (API cu credit lunar)",
        tip_api="anthropic",
        url_baza="https://api.anthropic.com",
        cheie_env="AMA_CHEIE_ANTHROPIC",
        platit=True,
        uz_comercial=True,
        antrenare_pe_date=False,
        restrictii_regionale="",
        note="Consiliul (T4) rulează în afara căii critice (ADR-06). Pe Max/Ultra creditul lunar este de "
        "100/200 USD; "
        "la epuizare cererile se opresc, nu se taxează. Apelurile se opresc din butonul „apeluri plătite”.",
        marcaj="I",
        verificat_la=None,
        sursa="https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-ultra-and-team-plans",
    ),
)

MODELE: tuple[ModelSeed, ...] = (
    ModelSeed(
        "openrouter",
        "meta-llama/llama-3.3-70b-instruct:free",
        "Llama 3.3 70B (gratuit)",
        "T3",
        131_072,
        (),
        Limite(),
        0.60,
        0.80,
        "I",
        None,
        "https://openrouter.ai/docs/limits",
        "Limitele sunt ale furnizorului (cont).",
    ),
    ModelSeed(
        "openrouter",
        "openai/gpt-oss-20b:free",
        "gpt-oss 20B (gratuit)",
        "T2",
        131_072,
        ("iesire_structurata",),
        Limite(),
        0.10,
        0.50,
        "I",
        None,
        "https://openrouter.ai/docs/limits",
        "Limitele sunt ale furnizorului (cont).",
    ),
    ModelSeed(
        "groq",
        "llama-3.3-70b-versatile",
        "Llama 3.3 70B",
        "T3",
        131_072,
        (),
        Limite(cereri_minut=30, cereri_zi=1000, tokeni_zi=200_000),
        0.60,
        0.80,
        "S",
        VERIFICAT,
        "https://console.groq.com/docs/rate-limits",
        "Exemplu de limite din documentație, pe model.",
    ),
    ModelSeed(
        "groq",
        "llama-3.1-8b-instant",
        "Llama 3.1 8B",
        "T1",
        131_072,
        (),
        Limite(cereri_minut=30, cereri_zi=1000, tokeni_zi=200_000),
        0.05,
        0.08,
        "I",
        None,
        "https://console.groq.com/docs/rate-limits",
        "Limitele sunt luate după exemplul din documentație.",
    ),
    ModelSeed(
        "gemini",
        "gemini-2.5-flash",
        "Gemini 2.5 Flash",
        "T2",
        1_048_576,
        ("iesire_structurata", "viziune", "unelte"),
        Limite(),
        0.30,
        2.50,
        "I",
        None,
        "https://ai.google.dev/gemini-api/docs/rate-limits",
        "Nu se folosește în producție pe nivelul gratuit.",
    ),
    ModelSeed(
        "cloudflare",
        "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        "Llama 3.3 70B (Workers AI)",
        "T3",
        24_000,
        (),
        Limite(),
        0.29,
        2.25,
        "I",
        None,
        "https://developers.cloudflare.com/workers-ai/platform/pricing/",
    ),
    ModelSeed(
        "anthropic",
        "claude-sonnet-4-5",
        "Claude Sonnet",
        "T3",
        200_000,
        ("iesire_structurata", "unelte", "viziune"),
        Limite(),
        3.0,
        15.0,
        "I",
        None,
        "https://docs.claude.com/en/docs/about-claude/models",
        "Identificator de confirmat la inventar.",
    ),
    ModelSeed(
        "anthropic",
        "claude-opus-4-5",
        "Claude Opus",
        "T4",
        200_000,
        ("iesire_structurata", "unelte", "viziune"),
        Limite(),
        5.0,
        25.0,
        "I",
        None,
        "https://docs.claude.com/en/docs/about-claude/models",
        "Consiliu: doar în afara căii critice. Identificator de confirmat la inventar.",
    ),
)


def valideaza() -> list[str]:
    """Probleme ale inventarului (listă goală = în regulă). Rulat de un test."""
    probleme: list[str] = []
    coduri: set[str] = set()
    for f in FURNIZORI:
        if not COD.match(f.cod) or f.cod in coduri:
            probleme.append(f"cod furnizor nepermis sau dublat: {f.cod!r}")
        coduri.add(f.cod)
        if f.tip_api not in TIPURI_API:
            probleme.append(f"{f.cod}: tip API necunoscut {f.tip_api!r}")
        if not NUME_VARIABILA.match(f.cheie_env):
            probleme.append(f"{f.cod}: variabila de mediu trebuie să se potrivească cu AMA_CHEIE_*")
        if f.marcaj not in MARCAJE:
            probleme.append(f"{f.cod}: marcaj necunoscut {f.marcaj!r}")
        if f.marcaj in ("V", "S") and f.verificat_la is None:
            probleme.append(f"{f.cod}: un fapt verificat are dată de verificare")
        if f.marcaj == "I" and f.verificat_la is not None:
            probleme.append(f"{f.cod}: o presupunere (I) nu are dată de verificare")
        if not f.url_baza.startswith("https://"):
            probleme.append(f"{f.cod}: adresa de bază trebuie să fie https")
    chei: set[tuple[str, str]] = set()
    for m in MODELE:
        if m.furnizor not in coduri:
            probleme.append(f"model {m.identificator}: furnizor necunoscut {m.furnizor!r}")
        if (m.furnizor, m.identificator) in chei:
            probleme.append(f"model dublat: {m.furnizor}/{m.identificator}")
        chei.add((m.furnizor, m.identificator))
        if m.nivel not in NIVELURI:
            probleme.append(f"{m.identificator}: nivel necunoscut {m.nivel!r}")
        if not set(m.capabilitati) <= set(CAPABILITATI):
            probleme.append(f"{m.identificator}: capabilitate necunoscută")
        if m.marcaj not in MARCAJE:
            probleme.append(f"{m.identificator}: marcaj necunoscut")
        if m.marcaj in ("V", "S") and m.verificat_la is None:
            probleme.append(f"{m.identificator}: un fapt verificat are dată de verificare")
        if m.marcaj == "I" and m.verificat_la is not None:
            probleme.append(f"{m.identificator}: o presupunere (I) nu are dată de verificare")
    return probleme
