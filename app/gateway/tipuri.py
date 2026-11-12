"""Tipurile comune ale clientului unificat: mesaje, cerere, răspuns, antete de limită, destinația unui apel.

Nimic aici nu poartă o cheie de API: cheia se dă clientului la trimitere și rămâne în antetul cererii.
"""

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal

Rol = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Mesaj:
    rol: Rol
    continut: str


@dataclass(frozen=True)
class Destinatie:
    """Ce trebuie să știe clientul despre un model: furnizorul, API-ul, adresa, parametrii (fără secrete)."""

    furnizor: str  # codul din registru
    tip_api: str
    url_baza: str
    model: str  # identificatorul la furnizor
    parametri: dict[str, Any] = field(default_factory=dict)
    capabilitati: frozenset[str] = frozenset()

    @property
    def schema_nativa(self) -> bool:
        return "iesire_structurata" in self.capabilitati


@dataclass(frozen=True)
class CerereModel:
    mesaje: tuple[Mesaj, ...]
    max_tokeni: int = 1024
    temperatura: float = 0.2
    schema_json: dict[str, Any] | None = None  # doar dacă modelul o suportă nativ
    schema_nume: str = "iesire"


@dataclass(frozen=True)
class AntetLimita:
    """Ce spune furnizorul despre limitele lui, normalizat (3.3 le folosește ca sursă de adevăr)."""

    ramas_cereri: int | None = None
    ramas_tokeni: int | None = None
    limita_cereri: int | None = None
    limita_tokeni: int | None = None
    reset_cereri_la: dt.datetime | None = None
    reset_tokeni_la: dt.datetime | None = None
    retry_dupa_sec: float | None = None

    @property
    def gol(self) -> bool:
        return self == AntetLimita()


@dataclass(frozen=True)
class RaspunsModel:
    text: str
    tokeni_intrare: int
    tokeni_iesire: int
    antete: AntetLimita = field(default_factory=AntetLimita)
    durata_ms: int = 0
    motiv_oprire: str = ""
    tokeni_pe_sec: float | None = None  # viteza de generare raportată de serverul local (llama.cpp `timings`)
