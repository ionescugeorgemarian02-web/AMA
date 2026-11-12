"""Adaptorul „chat completions” compatibil OpenAI: numitorul comun (OpenRouter, Groq, Cloudflare Workers
AI, un
server local compatibil). Diferențele dintre ei sunt DATE în registru (adresa, antetele de limită,
capabilitatea
`iesire_structurata`), nu ramuri de cod.
"""

import datetime as dt
from typing import Any, ClassVar

import httpx

from app.gateway import antete as antete_limita
from app.gateway.adaptoare.baza import clasifica, json_sau_gol
from app.gateway.erori import EroareFurnizor
from app.gateway.tipuri import CerereModel, Destinatie, RaspunsModel


def adresa(dest: Destinatie, cale: str) -> str:
    """Adresa de bază cu parametrii (fără secrete) puși în locul marcajelor `{nume}`; marcaj nerezolvat =
    eroare de
    configurare, nu o cerere trimisă greșit."""
    baza = dest.url_baza
    for k, v in dest.parametri.items():
        if isinstance(v, str) and v:
            baza = baza.replace("{" + k + "}", v)
    if "{" in baza:
        raise EroareFurnizor("cerere", detaliu="parametru lipsă în adresa furnizorului")
    return baza.rstrip("/") + cale


class OpenAICompat:
    tip_api: ClassVar[str] = "openai_compat"

    def cerere(self, dest: Destinatie, cheie: str | None, cerere: CerereModel) -> httpx.Request:
        corp: dict[str, Any] = {
            "model": dest.model,
            "messages": [{"role": m.rol, "content": m.continut} for m in cerere.mesaje],
            "max_tokens": cerere.max_tokeni,
            "temperature": cerere.temperatura,
        }
        if cerere.schema_json is not None:
            corp["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": cerere.schema_nume, "schema": cerere.schema_json, "strict": False},
            }
        antete = {"Authorization": f"Bearer {cheie}"} if cheie else {}
        return httpx.Request("POST", adresa(dest, "/chat/completions"), headers=antete, json=corp)

    def raspuns(self, raspuns: httpx.Response, acum: dt.datetime) -> RaspunsModel:
        corp = json_sau_gol(raspuns)
        if not isinstance(corp, dict):
            raise EroareFurnizor("server", status=raspuns.status_code, detaliu="răspuns care nu e JSON")
        if not corp.get("choices") and isinstance(corp.get("error"), dict):
            # OpenRouter poate răspunde 200 cu o eroare în corp
            cod = corp["error"].get("code")
            sintetic = httpx.Response(
                int(cod) if isinstance(cod, int) else 502, headers=raspuns.headers, json=corp
            )
            raise clasifica(sintetic, corp, acum)
        try:
            alegere = corp["choices"][0]
            text = alegere["message"].get("content") or ""
            utilizare = corp.get("usage") or {}
            return RaspunsModel(
                text=str(text),
                tokeni_intrare=int(utilizare.get("prompt_tokens", 0)),
                tokeni_iesire=int(utilizare.get("completion_tokens", 0)),
                antete=antete_limita.citeste(raspuns.headers, acum),
                motiv_oprire=str(alegere.get("finish_reason") or ""),
            )
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise EroareFurnizor(
                "server", status=raspuns.status_code, detaliu="formă de răspuns neașteptată"
            ) from None
