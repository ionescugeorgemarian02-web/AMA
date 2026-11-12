"""# SIMULAT: furnizorul fals de modele (F3.2). Nicio cheie reală, nicio rețea, nicio cotă consumată.

Un `httpx.MockTransport` care răspunde în forma REALĂ a fiecărui API (chat completions compatibil OpenAI, Gemini
`generateContent`, Anthropic Messages), după calea cererii. Comportamentul se scriptează PE GAZDĂ (un furnizor =
o gazdă): fiecare cerere către gazdă consumă următorul cuvânt din lista ei, iar când lista s-a golit se aplică
cuvântul permanent (implicit `ok`):

    fals = FurnizorFals()
    fals.scenariu("api.groq.com", "429", "ok")             # prima cerere: limită, a doua: reușită
    fals.scenariu("api.anthropic.com", permanent="401")      # toate: autentificare
    client.seteaza_transport(fals.transport)

Cuvinte: `ok` · `429` (cu antetele de limită ale API-ului) · `5xx` (500; 529 la Anthropic) · `timeout` · `json_invalid`
(text trunchiat) · `schema_gresita` (JSON valid, schema încălcată) · `401` · `400` (cerere respinsă) ·
`continut_blocat` (Gemini: blocat de filtre). Textul unui răspuns `ok` este `fals.text` (șir sau funcție de cerere).
Se păstrează toate cererile primite (`fals.cereri`), cu antetele și corpul, pentru testele de contract.
"""

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

TEXT_IMPLICIT = '{"eticheta": "pozitiv", "dovezi": ["recenzie entuziasta"], "incredere": 0.9}'


@dataclass
class CerereInregistrata:
    gazda: str
    cale: str
    antete: dict[str, str]
    corp: dict[str, Any]
    api: str  # openai | gemini | anthropic

    @property
    def text_prompt(self) -> str:
        return json.dumps(self.corp, ensure_ascii=False)


@dataclass
class FurnizorFals:
    text: str | Callable[[CerereInregistrata], str] = TEXT_IMPLICIT
    tokeni: tuple[int, int] | None = None  # (intrare, ieșire) fixe; altfel din lungimi
    antete_limita: bool = True
    dim_vectori: int = 8  # dimensiunea vectorilor întorși la `/embeddings`
    vectorizator: Callable[[str, int], list[float]] | None = (
        None  # înlocuiește vectorii hash (F4.3: sac de cuvinte)
    )
    timings: dict[str, float] | None = None  # câmpul `timings` al serverului local (llama.cpp)
    antete_ok: dict[str, str] | None = None  # înlocuiește antetele de limită ale unui răspuns reușit
    cereri: list[CerereInregistrata] = field(default_factory=list)
    _liste: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    _permanent: dict[str, str] = field(default_factory=dict)

    def scenariu(self, gazda: str, *cuvinte: str, permanent: str | None = None) -> None:
        self._liste[gazda] = list(cuvinte)
        if permanent is not None:
            self._permanent[gazda] = permanent
        else:
            self._permanent.pop(gazda, None)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._raspunde)

    def cereri_la(self, gazda: str) -> list[CerereInregistrata]:
        return [c for c in self.cereri if c.gazda == gazda]

    # --- implementare

    def _raspunde(self, cerere: httpx.Request) -> httpx.Response:
        gazda, cale = cerere.url.host, cerere.url.path
        api = (
            "gemini"
            if ":generateContent" in cale
            else "anthropic"
            if cale.endswith("/v1/messages")
            else "openai"
        )
        corp = json.loads(cerere.content) if cerere.content else {}
        inreg = CerereInregistrata(gazda, cale, dict(cerere.headers), corp, api)
        self.cereri.append(inreg)
        lista = self._liste[gazda]
        cuvant = lista.pop(0) if lista else self._permanent.get(gazda, "ok")
        if cale.endswith("/embeddings"):
            return self._vectori(inreg, cuvant, cerere)
        if cuvant == "timeout":
            raise httpx.ReadTimeout("timeout simulat", request=cerere)
        if cuvant in ("429", "5xx", "401", "400"):
            return self._eroare(api, cuvant)
        if cuvant == "continut_blocat":
            return httpx.Response(
                200, json={"promptFeedback": {"blockReason": "SAFETY"}, "usageMetadata": {}}
            )
        text = {
            "json_invalid": '{"eticheta": "pozitiv", "dovezi": [',
            "schema_gresita": '{"eticheta": 5}',
        }.get(cuvant)
        if text is None:
            text = self.text(inreg) if callable(self.text) else self.text
        return self._ok(api, inreg, text)

    def _vectori(self, inreg: CerereInregistrata, cuvant: str, cerere: httpx.Request) -> httpx.Response:
        if cuvant == "timeout":
            raise httpx.ReadTimeout("timeout simulat", request=cerere)
        if cuvant in ("5xx", "429", "401", "400"):
            return self._eroare("openai", cuvant)
        texte = inreg.corp.get("input", [])
        date = [
            {
                "object": "embedding",
                "index": i,
                "embedding": (self.vectorizator or _vector)(t, self.dim_vectori),
            }
            for i, t in enumerate(texte)
        ]
        corp = {"object": "list", "data": date, "model": inreg.corp.get("model", "model"),
                "usage": {"prompt_tokens": sum(max(1, len(t) // 4) for t in texte), "total_tokens": 0}}  # fmt: skip
        return httpx.Response(200, json=corp)

    def _tokeni(self, inreg: CerereInregistrata, text: str) -> tuple[int, int]:
        if self.tokeni is not None:
            return self.tokeni
        intrare = max(1, len(inreg.text_prompt) // 4)
        return intrare, max(1, len(text) // 4)

    def _ok(self, api: str, inreg: CerereInregistrata, text: str) -> httpx.Response:
        intrare, iesire = self._tokeni(inreg, text)
        antete: dict[str, str] = {}
        if api == "openai":
            if self.antete_limita:
                antete = {
                    "x-ratelimit-limit-requests": "1000",
                    "x-ratelimit-remaining-requests": "999",
                    "x-ratelimit-limit-tokens": "12000",
                    "x-ratelimit-remaining-tokens": "11800",
                    "x-ratelimit-reset-requests": "1m26.4s",
                    "x-ratelimit-reset-tokens": "7.66s",
                }
            corp: dict[str, Any] = {
                "id": "chatcmpl-9fakeA1B2C3",
                "object": "chat.completion",
                "created": 1_762_940_000,
                "model": inreg.corp.get("model", "model"),
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
                ],
                "usage": {
                    "prompt_tokens": intrare,
                    "completion_tokens": iesire,
                    "total_tokens": intrare + iesire,
                },
            }
            if self.timings is not None:
                corp["timings"] = self.timings
        elif api == "gemini":
            corp = {
                "candidates": [
                    {
                        "content": {"parts": [{"text": text}], "role": "model"},
                        "finishReason": "STOP",
                        "index": 0,
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": intrare,
                    "candidatesTokenCount": iesire,
                    "totalTokenCount": intrare + iesire,
                },
                "modelVersion": "gemini-2.5-flash",
            }
        else:
            if self.antete_limita:
                antete = {
                    "anthropic-ratelimit-requests-limit": "50",
                    "anthropic-ratelimit-requests-remaining": "49",
                    "anthropic-ratelimit-requests-reset": "2026-11-12T12:00:30Z",
                    "anthropic-ratelimit-tokens-limit": "40000",
                    "anthropic-ratelimit-tokens-remaining": "39000",
                    "anthropic-ratelimit-tokens-reset": "2026-11-12T12:00:30Z",
                }
            if "tools" in inreg.corp and _este_json(text):
                continut: list[dict[str, Any]] = [
                    {
                        "type": "tool_use",
                        "id": "toolu_01fakeA1B2",
                        "name": inreg.corp["tools"][0]["name"],
                        "input": json.loads(text),
                    }
                ]
                oprire = "tool_use"
            else:
                continut = [{"type": "text", "text": text}]
                oprire = "end_turn"
            corp = {
                "id": "msg_01fakeA1B2C3",
                "type": "message",
                "role": "assistant",
                "model": inreg.corp.get("model", "model"),
                "content": continut,
                "stop_reason": oprire,
                "usage": {"input_tokens": intrare, "output_tokens": iesire},
            }
        return httpx.Response(
            200, json=corp, headers=self.antete_ok if self.antete_ok is not None else antete
        )

    def _eroare(self, api: str, cuvant: str) -> httpx.Response:
        if cuvant == "429":
            if api == "openai":
                antete = {"retry-after": "7"}
                if self.antete_limita:
                    antete |= {
                        "x-ratelimit-limit-requests": "1000",
                        "x-ratelimit-remaining-requests": "0",
                        "x-ratelimit-reset-requests": "7s",
                    }
                corp = {
                    "error": {
                        "message": "Rate limit reached for model in organization org_x on requests per day.",
                        "type": "requests",
                        "code": "rate_limit_exceeded",
                    }
                }
                return httpx.Response(429, json=corp, headers=antete)
            if api == "gemini":
                corp = {
                    "error": {
                        "code": 429,
                        "message": "Resource has been exhausted (e.g. check quota).",
                        "status": "RESOURCE_EXHAUSTED",
                        "details": [
                            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "34s"}
                        ],
                    }
                }
                return httpx.Response(429, json=corp)
            corp = {
                "type": "error",
                "error": {"type": "rate_limit_error", "message": "This request would exceed the rate limit."},
            }
            return httpx.Response(429, json=corp, headers={"retry-after": "12"})
        if cuvant == "5xx":
            if api == "anthropic":
                corp = {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}
                return httpx.Response(529, json=corp)
            if api == "gemini":
                corp = {
                    "error": {"code": 503, "message": "The model is overloaded.", "status": "UNAVAILABLE"}
                }
                return httpx.Response(503, json=corp)
            return httpx.Response(
                500, json={"error": {"message": "Internal server error", "type": "server_error"}}
            )
        if cuvant == "401":
            if api == "anthropic":
                corp = {
                    "type": "error",
                    "error": {"type": "authentication_error", "message": "invalid x-api-key"},
                }
                return httpx.Response(401, json=corp)
            if api == "gemini":
                corp = {
                    "error": {
                        "code": 403,
                        "message": "API key was reported as leaked.",
                        "status": "PERMISSION_DENIED",
                    }
                }
                return httpx.Response(403, json=corp)
            return httpx.Response(
                401,
                json={
                    "error": {
                        "message": "Invalid API Key",
                        "type": "invalid_request_error",
                        "code": "invalid_api_key",
                    }
                },
            )
        corp = {
            "error": {
                "message": "prompt too long",
                "type": "invalid_request_error",
                "code": "context_length_exceeded",
            }
        }
        return httpx.Response(400, json=corp)


def _este_json(text: str) -> bool:
    try:
        json.loads(text)
    except ValueError:
        return False
    return True


def _vector(text: str, dim: int) -> list[float]:
    """Un vector determinist din text (același text, același vector)."""
    h = hashlib.sha256(text.encode()).digest()
    return [round((h[i % len(h)] - 128) / 128, 4) for i in range(dim)]


def numere_din(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"\d+", text)]
