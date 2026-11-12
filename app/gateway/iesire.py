"""Ieșiri structurate (8.6): schema, validarea răspunsului și cererea de reparație. Pur: fără rețea, fără
bază.

Orice schemă de ieșire moștenește `Iesire` (câmpuri obligatorii în orice ieșire: dovezi și încredere;
rezultatul îl
declară fiecare schemă; versiunea promptului o știe gateway-ul și o pune pe `Rezultat`). Un răspuns este
valid doar
dacă trece prin `model_validate`. Mesajele de eroare spun CE câmp e greșit, nu repetă valorile primite (pot
fi date
de client): se trimit modelului la reparație și se păstrează în jurnal.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.gateway.tipuri import Mesaj

LUNGIME_MAXIMA_EROARE = 800
GARDURI = re.compile(r"^\s*```(?:json|JSON)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


class Iesire(BaseModel):
    """Baza schemelor de ieșire. Valorile în plus sunt interzise (schema JSON are `additionalProperties:
    false`)."""

    model_config = ConfigDict(extra="forbid")

    dovezi: list[str] = Field(default_factory=list, description="Pe ce se sprijină rezultatul")
    incredere: float = Field(ge=0.0, le=1.0, description="Încrederea în rezultat, între 0 și 1")


def cheie_schema(schema: type[BaseModel]) -> str:
    """Identificatorul stabil al unei scheme (se scrie în registrul de prompturi și în jurnal)."""
    return f"{schema.__module__}.{schema.__qualname__}"


def schema_json(schema: type[BaseModel]) -> dict[str, Any]:
    return schema.model_json_schema()


def extrage_json(text: str) -> str:
    """Scoate gardurile de cod și textul din jurul primului obiect JSON (modelele fără mod JSON le adaugă)."""
    t = text.strip()
    m = GARDURI.match(t)
    if m:
        t = m.group(1).strip()
    if not t.startswith(("{", "[")):
        start = t.find("{")
        sfarsit = t.rfind("}")
        if start != -1 and sfarsit > start:
            t = t[start : sfarsit + 1]
    return t


@dataclass(frozen=True)
class Verdict:
    obiect: Iesire | None
    eroare: str = ""  # goală dacă răspunsul e valid

    @property
    def valid(self) -> bool:
        return self.obiect is not None


def valideaza[S: Iesire](text: str, schema: type[S]) -> Verdict:
    try:
        date = json.loads(extrage_json(text))
    except json.JSONDecodeError as exc:
        return Verdict(None, f"JSON invalid: {exc.msg} (linia {exc.lineno}, coloana {exc.colno})")
    try:
        return Verdict(schema.model_validate(date))
    except ValidationError as exc:
        return Verdict(None, _eroare_scurta(exc))


def _eroare_scurta(exc: ValidationError) -> str:
    parti = []
    for e in exc.errors(include_input=False, include_url=False, include_context=False):
        cale = ".".join(str(p) for p in e["loc"]) or "(rădăcină)"
        parti.append(f"{cale}: {e['msg']}")
    return "; ".join(parti)[:LUNGIME_MAXIMA_EROARE]


def instructiune_schema(schema: dict[str, Any]) -> str:
    """Pentru modelele fără ieșire structurată nativă: schema intră în instrucțiuni (8.6)."""
    return (
        "Răspunde EXCLUSIV cu un singur obiect JSON valid, fără text în jur și fără blocuri de cod, "
        "care respectă această schemă JSON:\n" + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    )


def cu_instructiune(mesaje: tuple[Mesaj, ...], schema: dict[str, Any]) -> tuple[Mesaj, ...]:
    """Adaugă instrucțiunea de schemă la mesajul de sistem (sau creează unul)."""
    instr = instructiune_schema(schema)
    if mesaje and mesaje[0].rol == "system":
        return (Mesaj("system", mesaje[0].continut + "\n\n" + instr), *mesaje[1:])
    return (Mesaj("system", instr), *mesaje)


def cerere_reparatie(mesaje: tuple[Mesaj, ...], raspuns_gresit: str, eroare: str) -> tuple[Mesaj, ...]:
    """Conversația de reparație (8.6): răspunsul greșit al modelului și eroarea exactă, cu cererea de a-l
    corecta."""
    return (
        *mesaje,
        Mesaj("assistant", raspuns_gresit),
        Mesaj(
            "user",
            "Răspunsul anterior nu respectă schema cerută. Eroarea exactă: "
            f"{eroare}\nReîntoarce DOAR obiectul JSON corectat, complet, fără alt text.",
        ),
    )
