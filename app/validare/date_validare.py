"""Datele validatorilor (limite pe canal, liste de cuvinte, praguri) trăiesc în fișiere TOML din
`app/validare/date/`,
nu în `if`-uri. Se încarcă o dată (`tomllib`, biblioteca standard) și se validează la încărcare: o greșeală
de scriere în
date oprește aplicația la pornire / la test, nu produce verdicte greșite pe tăcute."""

import functools
import tomllib
from pathlib import Path
from typing import Any

DIRECTOR = Path(__file__).resolve().parent / "date"


class DateInvalide(ValueError):
    pass


@functools.cache
def incarca(nume: str) -> dict[str, Any]:
    cale = DIRECTOR / f"{nume}.toml"
    try:
        with cale.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise DateInvalide(f"{cale.name}: {exc}") from exc
