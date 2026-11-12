"""Adaptorul Anthropic Messages. Ieșirea structurată se cere prin „tool use” forțat: modelul răspunde cu
argumentele
unei unelte a cărei schemă de intrare este schema ieșirii."""

import datetime as dt
import json
from typing import Any, ClassVar

import httpx

from app.gateway import antete as antete_limita
from app.gateway.adaptoare.baza import json_sau_gol
from app.gateway.adaptoare.openai_compat import adresa
from app.gateway.erori import EroareFurnizor
from app.gateway.tipuri import CerereModel, Destinatie, RaspunsModel

VERSIUNE_API = "2023-06-01"
UNEALTA = "raspuns_structurat"


class Anthropic:
    tip_api: ClassVar[str] = "anthropic"

    def cerere(self, dest: Destinatie, cheie: str | None, cerere: CerereModel) -> httpx.Request:
        sistem = "\n\n".join(m.continut for m in cerere.mesaje if m.rol == "system")
        corp: dict[str, Any] = {
            "model": dest.model,
            "max_tokens": cerere.max_tokeni,
            "temperature": cerere.temperatura,
            "messages": [{"role": m.rol, "content": m.continut} for m in cerere.mesaje if m.rol != "system"],
        }
        if sistem:
            corp["system"] = sistem
        if cerere.schema_json is not None:
            corp["tools"] = [
                {
                    "name": UNEALTA,
                    "description": "Întoarce răspunsul în forma cerută.",
                    "input_schema": cerere.schema_json,
                }
            ]
            corp["tool_choice"] = {"type": "tool", "name": UNEALTA}
        antete = {"anthropic-version": VERSIUNE_API}
        if cheie:
            antete["x-api-key"] = cheie
        return httpx.Request("POST", adresa(dest, "/v1/messages"), headers=antete, json=corp)

    def raspuns(self, raspuns: httpx.Response, acum: dt.datetime) -> RaspunsModel:
        corp = json_sau_gol(raspuns)
        if not isinstance(corp, dict) or not isinstance(corp.get("content"), list):
            raise EroareFurnizor("server", status=raspuns.status_code, detaliu="formă de răspuns neașteptată")
        try:
            text = ""
            for bloc in corp["content"]:
                if bloc.get("type") == "tool_use":
                    text = json.dumps(bloc.get("input", {}), ensure_ascii=False)
                    break
                if bloc.get("type") == "text":
                    text += str(bloc.get("text", ""))
            utilizare = corp.get("usage") or {}
            return RaspunsModel(
                text=text,
                tokeni_intrare=int(utilizare.get("input_tokens", 0)),
                tokeni_iesire=int(utilizare.get("output_tokens", 0)),
                antete=antete_limita.citeste(raspuns.headers, acum),
                motiv_oprire=str(corp.get("stop_reason") or ""),
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            raise EroareFurnizor(
                "server", status=raspuns.status_code, detaliu="formă de răspuns neașteptată"
            ) from None
