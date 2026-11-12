"""Adaptorul `local` (F3.5): un server de inferență compatibil OpenAI rulat SEPARAT (llama.cpp
`llama-server` sau Ollama), în rețeaua internă. Fără biblioteci grele în imaginea aplicației: aplicația
vorbește cu serverul prin HTTP, ca cu orice alt furnizor.

Diferențe față de numitorul comun OpenAI:
- fără cheie (serverul nu e expus în afara rețelei interne);
- `cache_prompt` (llama.cpp reutilizează prefixul promptului între cereri) și răspuns fără flux;
- ieșire structurată prin decodare constrânsă de gramatică: schema JSON a cererii intră în
  `response_format` și serverul generează DOAR text care o respectă (8.6); modelul are deci capabilitatea
  `iesire_structurata`;
- viteza de generare raportată de server (`timings.predicted_per_second` la llama.cpp), folosită la măsurare;
- vectori (`/embeddings`) pentru modelul de vectori, tot pe un server separat (10.5).
Timpul maxim al cererii vine din parametrii furnizorului (`timeout_sec`): pe procesor, generarea durează
minute.
"""

import datetime as dt
from dataclasses import replace
from typing import Any, ClassVar

import httpx

from app.gateway.adaptoare.baza import json_sau_gol
from app.gateway.adaptoare.openai_compat import OpenAICompat, adresa
from app.gateway.erori import EroareFurnizor
from app.gateway.tipuri import CerereModel, Destinatie, RaspunsModel


class Local(OpenAICompat):
    tip_api: ClassVar[str] = "local"

    def corp(self, dest: Destinatie, cerere: CerereModel) -> dict[str, Any]:
        corp = super().corp(dest, cerere)
        corp["stream"] = False
        corp["cache_prompt"] = True
        return corp

    def raspuns(self, raspuns: httpx.Response, acum: dt.datetime) -> RaspunsModel:
        r = super().raspuns(raspuns, acum)
        corp = json_sau_gol(raspuns)
        timings = corp.get("timings") if isinstance(corp, dict) else None
        viteza = timings.get("predicted_per_second") if isinstance(timings, dict) else None
        if isinstance(viteza, int | float) and not isinstance(viteza, bool) and viteza > 0:
            return replace(r, tokeni_pe_sec=float(viteza))
        return r

    # --- vectori

    def cerere_vectori(self, dest: Destinatie, texte: list[str]) -> httpx.Request:
        return httpx.Request("POST", adresa(dest, "/embeddings"), json={"model": dest.model, "input": texte})

    def raspuns_vectori(self, raspuns: httpx.Response, asteptate: int) -> tuple[list[list[float]], int]:
        """(vectorii în ordinea textelor, tokeni de intrare). Orice abatere de la formă este o eroare de
        server."""
        corp = json_sau_gol(raspuns)
        try:
            date = sorted(corp["data"], key=lambda d: d.get("index", 0))
            vectori = [[float(x) for x in d["embedding"]] for d in date]
            tokeni = int((corp.get("usage") or {}).get("prompt_tokens", 0))
        except (KeyError, TypeError, ValueError, AttributeError):
            raise EroareFurnizor("server", detaliu="formă de răspuns neașteptată (vectori)") from None
        if len(vectori) != asteptate:
            raise EroareFurnizor("server", detaliu="număr de vectori diferit de numărul de texte")
        return vectori, tokeni
