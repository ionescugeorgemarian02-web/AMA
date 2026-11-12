"""Profilurile de sarcină (8.2) ca DATE: nivel minim, capabilități cerute, lanțul ordonat de modele și ce
se întâmplă
când lanțul s-a epuizat. Sămânța de aici intră în tabelul `gateway_profiluri` (migrarea `0014`); după aceea se
editează în registru (ecranul bogat vine cu F3.10).

Intrările unui lanț sunt `furnizor/identificator` (un model anume) sau `nivel:<T1|T2|T3|T4|local>` (orice
model de
acel nivel, ordonat după scor). Un model pe care registrul nu-l cunoaște încă (de exemplu cel local, F3.5) se
sare, nu strică profilul.

`la_epuizare`:
- `amana`: lanțul principal epuizat → `Amanat`; niciodată un model mai slab (strategie, creație, judecată);
- `degradeaza`: se folosește `lant_degradare` (de exemplu modelul local), marcat `degradat` (clasificare,
rescriere);
- `amana_sau_provizoriu`: `Amanat`, sau `lant_degradare` marcat `provizoriu` DACĂ apelantul acceptă
(consiliu).
"""

import re
from dataclasses import dataclass
from typing import Literal

NUME_PROFIL = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
INTRARE_LANT = re.compile(r"^([a-z][a-z0-9_]{1,30}/\S{1,200}|nivel:(T1|T2|T3|T4|local))$")
LaEpuizare = Literal["amana", "degradeaza", "amana_sau_provizoriu"]
LA_EPUIZARE: tuple[str, ...] = ("amana", "degradeaza", "amana_sau_provizoriu")


@dataclass(frozen=True)
class Profil:
    nume: str
    eticheta: str
    descriere: str
    nivel_min: str
    capabilitati: frozenset[str]
    lant: tuple[str, ...]
    la_epuizare: str
    lant_degradare: tuple[str, ...] = ()
    verificare_in_plus: bool = False  # la degradare, rezultatul cere o verificare în plus (8.2, rescriere)


@dataclass(frozen=True)
class ProfilSeed:
    nume: str
    eticheta: str
    descriere: str
    nivel_min: str
    lant: tuple[str, ...]
    la_epuizare: str
    capabilitati: tuple[str, ...] = ()
    lant_degradare: tuple[str, ...] = ()
    verificare_in_plus: bool = False


GROQ_70B = "groq/llama-3.3-70b-versatile"
GROQ_8B = "groq/llama-3.1-8b-instant"
OR_70B = "openrouter/meta-llama/llama-3.3-70b-instruct:free"
OR_20B = "openrouter/openai/gpt-oss-20b:free"
CF_70B = "cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast"
CLAUDE_SONNET = "anthropic/claude-sonnet-4-5"
CLAUDE_OPUS = "anthropic/claude-opus-4-5"

PROFILURI: tuple[ProfilSeed, ...] = (
    ProfilSeed(
        "clasificare", "Clasificare și extragere",
        "Intenția unui comentariu, extragerea afirmațiilor. Dacă lipsește cota: modelul local.",
        "T1", (GROQ_8B, OR_20B, GROQ_70B), "degradeaza", lant_degradare=("nivel:local",),
    ),
    ProfilSeed(
        "rescriere", "Rescriere și adaptare",
        "Adaptare pe canal, editare. Dacă lipsește cota: alt furnizor T2, apoi local, cu o "
        "verificare în plus.",
        "T2", (OR_20B, GROQ_70B, CF_70B), "degradeaza", lant_degradare=("nivel:local",),
        verificare_in_plus=True,
    ),
    ProfilSeed(
        "creatie", "Creație",
        "Hook-uri, scripturi, postări. Dacă lipsește cota: alt furnizor; altfel amânare.",
        "T2", (GROQ_70B, OR_70B, CF_70B, CLAUDE_SONNET), "amana",
    ),
    ProfilSeed(
        "judecata", "Judecată",
        "Validatori cu rubrică: alt model decât autorul. Dacă lipsește cota: alt furnizor; altfel amânare.",
        "T2", (GROQ_70B, OR_70B, CF_70B, CLAUDE_SONNET), "amana",
    ),
    ProfilSeed(
        "strategie", "Strategie și sinteză",
        "Strategie, brief de insight, plan media. Dacă lipsește cota: amânare; niciodată un model mai slab.",
        "T3", (GROQ_70B, OR_70B, CF_70B, CLAUDE_SONNET), "amana",
    ),
    ProfilSeed(
        "consiliu", "Consiliu",
        "Decizii lunare și escaladări (T4), în afara căii critice (ADR-06). Amânare, sau T3 „provizoriu”.",
        "T4", (CLAUDE_OPUS,), "amana_sau_provizoriu", lant_degradare=("nivel:T3",),
    ),
)  # fmt: skip


def valideaza() -> list[str]:
    probleme: list[str] = []
    vazute: set[str] = set()
    for p in PROFILURI:
        if not NUME_PROFIL.match(p.nume) or p.nume in vazute:
            probleme.append(f"nume de profil nepermis sau dublat: {p.nume!r}")
        vazute.add(p.nume)
        if p.la_epuizare not in LA_EPUIZARE:
            probleme.append(f"{p.nume}: la_epuizare necunoscut")
        if not p.lant:
            probleme.append(f"{p.nume}: lanț gol")
        for intrare in (*p.lant, *p.lant_degradare):
            if not INTRARE_LANT.match(intrare):
                probleme.append(f"{p.nume}: intrare de lanț nepermisă {intrare!r}")
        if p.la_epuizare == "amana" and p.lant_degradare:
            probleme.append(f"{p.nume}: un profil care amână nu are lanț de degradare")
        if p.la_epuizare != "amana" and not p.lant_degradare:
            probleme.append(f"{p.nume}: lipsește lanțul de degradare")
    return probleme
