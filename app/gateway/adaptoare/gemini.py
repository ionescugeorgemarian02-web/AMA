"""Adaptorul Google Gemini (`generateContent`): alt format de cerere și de răspuns decât „chat
completions”."""

import datetime as dt
from typing import Any, ClassVar

import httpx

from app.gateway import antete as antete_limita
from app.gateway.adaptoare.baza import json_sau_gol
from app.gateway.adaptoare.openai_compat import adresa
from app.gateway.erori import EroareFurnizor
from app.gateway.tipuri import CerereModel, Destinatie, RaspunsModel


class Gemini:
    tip_api: ClassVar[str] = "gemini"

    def cerere(self, dest: Destinatie, cheie: str | None, cerere: CerereModel) -> httpx.Request:
        sistem = "\n\n".join(m.continut for m in cerere.mesaje if m.rol == "system")
        corp: dict[str, Any] = {
            "contents": [
                {"role": "model" if m.rol == "assistant" else "user", "parts": [{"text": m.continut}]}
                for m in cerere.mesaje
                if m.rol != "system"
            ],
            "generationConfig": {"maxOutputTokens": cerere.max_tokeni, "temperature": cerere.temperatura},
        }
        if sistem:
            corp["systemInstruction"] = {"parts": [{"text": sistem}]}
        if cerere.schema_json is not None:
            corp["generationConfig"]["responseMimeType"] = "application/json"
            corp["generationConfig"]["responseJsonSchema"] = cerere.schema_json
        antete = (
            {"x-goog-api-key": cheie} if cheie else {}
        )  # în antet, nu în adresă: adresele ajung în jurnale
        return httpx.Request(
            "POST", adresa(dest, f"/models/{dest.model}:generateContent"), headers=antete, json=corp
        )

    def raspuns(self, raspuns: httpx.Response, acum: dt.datetime) -> RaspunsModel:
        corp = json_sau_gol(raspuns)
        if not isinstance(corp, dict):
            raise EroareFurnizor("server", status=raspuns.status_code, detaliu="răspuns care nu e JSON")
        blocat = (corp.get("promptFeedback") or {}).get("blockReason")
        if blocat or not corp.get("candidates"):
            raise EroareFurnizor(
                "continut", status=raspuns.status_code, detaliu=str(blocat or "fără candidați")[:80]
            )
        try:
            candidat = corp["candidates"][0]
            parti = (candidat.get("content") or {}).get("parts") or []
            text = "".join(str(p.get("text", "")) for p in parti if isinstance(p, dict))
            utilizare = corp.get("usageMetadata") or {}
            return RaspunsModel(
                text=text,
                tokeni_intrare=int(utilizare.get("promptTokenCount", 0)),
                tokeni_iesire=int(utilizare.get("candidatesTokenCount", 0)),
                antete=antete_limita.citeste(raspuns.headers, acum),
                motiv_oprire=str(candidat.get("finishReason") or ""),
            )
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise EroareFurnizor(
                "server", status=raspuns.status_code, detaliu="formă de răspuns neașteptată"
            ) from None
