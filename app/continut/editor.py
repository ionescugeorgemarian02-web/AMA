"""Editorul (E8, F6.3, docs/13 §13.5), partea deterministă: ș / ț cu virgulă, ghilimele românești, spații,
formulări
șablon de la început de frază (`date/editor.toml`, [I]). Scopul este un text bun, nu păcălirea detectoarelor.

Editorul NU schimbă fapte: dacă afirmațiile verificabile (prețuri, cifre, termene, promisiuni; extrase ca la
G2) diferă
după editare, se păstrează textul original. G2 rulează oricum din nou în cascadă.
"""

import re
import tomllib
from functools import cache
from pathlib import Path
from typing import Any

from app import validare

DATE = Path(__file__).with_name("date") / "editor.toml"
SPATII = re.compile(r"[ \t]{2,}")
GHILIMELE = re.compile(r'"([^"\n]{1,200})"')


@cache
def _date() -> dict[str, Any]:
    with DATE.open("rb") as f:
        return tomllib.load(f)


def _fara_sabloane(text: str) -> str:
    for s in _date()["sabloane"]["inceput_de_fraza"]:
        tipar = re.compile(r"(^|(?<=[.!?…]\s)|(?<=\n))" + re.escape(s), re.IGNORECASE)

        def inlocuieste(m: re.Match[str]) -> str:
            return m.group(1)

        text = tipar.sub(inlocuieste, text)
    # după tăiere, fraza începe cu literă mare
    return re.sub(r"(^|[.!?…]\s+|\n)([a-zăâîșț])", lambda m: m.group(1) + m.group(2).upper(), text)


def _amprenta_fapte(text: str) -> list[tuple[str, str]]:
    return [(a.tip, a.fragment.lower()) for a in validare.extrage_afirmatii(text)]


def editeaza(text: str) -> str:
    """Textul editat; neschimbat dacă editarea ar atinge vreo afirmație verificabilă."""
    g = _date()["ghilimele"]
    nou = validare.corecteaza_sedila(text)
    nou = GHILIMELE.sub(lambda m: f"{g['deschise']}{m.group(1)}{g['inchise']}", nou)
    nou = _fara_sabloane(nou)
    nou = "\n".join(SPATII.sub(" ", linie).strip() for linie in nou.split("\n")).strip()
    if _amprenta_fapte(nou) != _amprenta_fapte(validare.corecteaza_sedila(text)):
        return validare.corecteaza_sedila(text).strip()
    return nou
