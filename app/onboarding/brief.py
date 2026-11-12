"""Brieful clientului (F4.4): câmpurile obligatorii ca schemă Pydantic și validarea de completitudine STRICTĂ.

Un brief are 11 câmpuri (docs/19 §19.3). Fiecare câmp are o valoare și cel puțin o sursă: răspunsul clientului
(rândul din interviu), un pasaj din materialele colectate sau intervenția unui operator. Un câmp lipsă, gol,
umplut cu un substitut („-”, „nu știu”, „n/a”), mai scurt decât minimul întrebării sau fără sursă
înseamnă brief
incomplet, iar un brief incomplet NU poate fi trimis spre aprobare: poarta compartimentului
(`creier.PoartaInchisa`)
o impune oricui încearcă, nu doar ecranului.

Nucleu pur: fără bază, fără model.
"""

import re
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.onboarding import interviu

CAMPURI: dict[str, str] = {
    "nume_brand": "Brand și domeniu",
    "ce_vinde": "Ce vinde",
    "preturi": "Prețuri",
    "public_tinta": "Cui vinde",
    "de_ce_ne_aleg": "De ce îl aleg clienții",
    "obiectii": "Obiecții auzite",
    "concurenti": "Concurenți",
    "ce_a_incercat": "Ce a încercat deja",
    "interdictii": "Ce nu trebuie să apară niciodată",
    "ton_dorit": "Ton dorit",
    "obiectiv_90_zile": "Obiectiv pe 90 de zile",
}
SUBSTITUTE = frozenset(
    {
        "",
        "-",
        "--",
        "n/a",
        "na",
        "nu stiu",
        "nimic",
        "orice",
        "de completat",
        "tbd",
        "ok",
        "da",
        "nu",
        "la fel",
        "idem",
    }
)
MIN_IMPLICIT = 20
SURSE_TIP = ("raspuns", "pasaj", "operator")


class SursaCamp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tip: Literal["raspuns", "pasaj", "operator"]
    ref: str = Field(max_length=100)  # rândul de răspuns, pasajul sau utilizatorul
    citat: str | None = Field(default=None, max_length=800)  # textul exact din răspuns / pasaj


class CampBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valoare: str = Field(max_length=2500)
    surse: list[SursaCamp] = Field(default_factory=list, max_length=6)


class BriefClient(BaseModel):
    """Brieful, câmp cu câmp. Câmpurile pot lipsi într-o ciornă; `lipsuri` spune ce nu e gata."""

    model_config = ConfigDict(extra="forbid")
    nume_brand: CampBrief | None = None
    ce_vinde: CampBrief | None = None
    preturi: CampBrief | None = None
    public_tinta: CampBrief | None = None
    de_ce_ne_aleg: CampBrief | None = None
    obiectii: CampBrief | None = None
    concurenti: CampBrief | None = None
    ce_a_incercat: CampBrief | None = None
    interdictii: CampBrief | None = None
    ton_dorit: CampBrief | None = None
    obiectiv_90_zile: CampBrief | None = None


def _simplu(text: str) -> str:
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9/ ]+", " ", t).strip()


def _doar_substitute(valoare: str) -> bool:
    """Toate rândurile sunt substitute („Nu știu”, „-” …), eventual repetate după clarificări."""
    return all(_simplu(rand) in SUBSTITUTE for rand in valoare.splitlines() if rand.strip())


def _minim(camp: str) -> int:
    for q in interviu.intrebari():
        if q.camp == camp:
            return q.min_caractere
    return MIN_IMPLICIT


def lipsuri(continut: dict[str, Any]) -> list[str]:
    """Problemele de completitudine, câte una pe rând (listă goală = brief complet). Strict: orice câmp
    lipsă / gol / substitut / prea scurt / fără sursă este o problemă."""
    probleme: list[str] = []
    for camp, nume in CAMPURI.items():
        c = continut.get(camp)
        if not isinstance(c, dict):
            probleme.append(f"{nume}: lipsește")
            continue
        valoare = str(c.get("valoare") or "").strip()
        if not valoare or not re.search(r"\w", valoare) or _doar_substitute(valoare):
            probleme.append(f"{nume}: gol sau fără conținut")
        elif len(valoare) < _minim(camp):
            probleme.append(f"{nume}: prea scurt ({len(valoare)} caractere; minim {_minim(camp)})")
        surse = c.get("surse")
        if not isinstance(surse, list) or not surse:
            probleme.append(f"{nume}: fără sursă")
    return probleme


def este_complet(continut: dict[str, Any]) -> bool:
    return not lipsuri(continut)


def numar_campuri_complete(continut: dict[str, Any]) -> int:
    nume_probleme = lipsuri(continut)
    return sum(1 for nume in CAMPURI.values() if not any(p.startswith(f"{nume}:") for p in nume_probleme))


def text_pentru_prompt(continut: dict[str, Any]) -> str:
    """Brieful ca text (pentru constructorul de context și prompturile următoare)."""
    return "\n".join(
        f"{nume}: {str((continut.get(camp) or {}).get('valoare', '')).strip()}"
        for camp, nume in CAMPURI.items()
        if isinstance(continut.get(camp), dict)
    )
