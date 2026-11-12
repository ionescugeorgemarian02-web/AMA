"""Criteriile automate ale testului comparativ pe română (8.10): nucleu pur, fără bază și fără rețea.

O sarcină declară criterii (ca date în `evaluare/sarcini/*.json`); scorul automat al unui răspuns este
media criteriilor, fiecare între 0 și 1. `schema_valida` e mereu primul criteriu: o ieșire în afara
schemei are scor 0.

Criterii: `lungime_min` / `lungime_max` (caractere, pe textul din `text_din` sau pe toate câmpurile text),
`cuvinte_obligatorii` (fracția găsită; comparație fără diacritice și fără majuscule, ca lipsa
diacriticelor să nu fie penalizată de două ori), `cuvinte_interzise` (1 dacă niciunul nu apare),
`raspuns_exact` (câmp = valoare, tot fără diacritice) și `diacritice` (română corectă: fără cedilă ş/ţ în
loc de virgulă ș/ț, fără cuvinte frecvente scrise fără diacritice, iar un text lung trebuie să conțină cel
puțin un semn diacritic). Verificările sunt euristice: un text bun poate pica izolat, dar compară modelele
între ele.
"""

import re
from dataclasses import dataclass
from typing import Any

PLIERE = str.maketrans("ăâîșțşţĂÂÎȘȚŞŢ", "aaistst" + "aaistst")
CEDILA = set("şţŞŢ")
DIACRITICE = set("ăâîșțĂÂÎȘȚ")
# Cuvinte frecvente care, scrise așa, arată că lipsesc diacriticele (nu sunt cuvinte românești valide).
FARA_DIACRITICE = frozenset(
    {"si", "dupa", "inca", "tara", "multumim", "fara", "clienti", "in", "pana", "sa", "cand", "intr"}
)
LUNGIME_DIACRITICE = 60  # sub această lungime nu se cere niciun semn diacritic
CUVANT = re.compile(r"\w+", re.UNICODE)


def plie(text: str) -> str:
    return text.translate(PLIERE).lower()


@dataclass(frozen=True)
class Evaluare:
    scor: float
    detalii: dict[str, float]


def text_din(iesire: dict[str, Any], camp: str | None) -> str:
    if camp:
        v = iesire.get(camp, "")
        return v if isinstance(v, str) else ""
    return "\n".join(v for k, v in iesire.items() if isinstance(v, str) and k != "dovezi")


def diacritice_corecte(text: str) -> bool:
    if any(c in CEDILA for c in text):
        return False
    if any(c in FARA_DIACRITICE for c in (w.lower() for w in CUVANT.findall(text))):
        return False
    return len(text) < LUNGIME_DIACRITICE or any(c in DIACRITICE for c in text)


def evalueaza(criterii: dict[str, Any], iesire: dict[str, Any] | None) -> Evaluare:
    if iesire is None:
        return Evaluare(0.0, {"schema_valida": 0.0})
    d: dict[str, float] = {"schema_valida": 1.0}
    text = text_din(iesire, criterii.get("text_din"))
    plan = plie(text)
    if "lungime_min" in criterii:
        d["lungime_min"] = 1.0 if len(text) >= criterii["lungime_min"] else 0.0
    if "lungime_max" in criterii:
        d["lungime_max"] = 1.0 if len(text) <= criterii["lungime_max"] else 0.0
    if criterii.get("cuvinte_obligatorii"):
        gasite = sum(1 for c in criterii["cuvinte_obligatorii"] if plie(c) in plan)
        d["cuvinte_obligatorii"] = round(gasite / len(criterii["cuvinte_obligatorii"]), 4)
    if criterii.get("cuvinte_interzise"):
        d["cuvinte_interzise"] = 0.0 if any(plie(c) in plan for c in criterii["cuvinte_interzise"]) else 1.0
    if "raspuns_exact" in criterii:
        r = criterii["raspuns_exact"]
        valoare = iesire.get(r["camp"])
        d["raspuns_exact"] = (
            1.0 if isinstance(valoare, str) and plie(valoare).strip() == plie(r["valoare"]) else 0.0
        )
    if criterii.get("diacritice"):
        d["diacritice"] = 1.0 if diacritice_corecte(text) else 0.0
    return Evaluare(round(sum(d.values()) / len(d), 4), d)


def scor_profil(automate: list[float], note_umane: list[int], pondere_umana: float) -> float | None:
    """Scorul unui model pe un profil (0–1): media scorurilor automate; dacă există note umane (1–5), se
    combină cu media lor normalizată, cu `pondere_umana`. `None` dacă nu există niciun rezultat."""
    if not automate:
        return None
    auto = sum(automate) / len(automate)
    if not note_umane:
        return round(auto, 4)
    umana = (sum(note_umane) / len(note_umane) - 1) / 4
    return round((1 - pondere_umana) * auto + pondere_umana * umana, 4)
