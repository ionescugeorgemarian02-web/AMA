"""Registrul conectorilor de efecte, pe canal (F2.5). Se importă DOAR din executor și din conectori
(garda `scripts/check_efecte.py`): restul aplicației cere efecte prin `app.operare.efecte.cere`."""

import importlib
from dataclasses import dataclass

from app.connectors.contract import Conector, ConectorSistem
from app.operare.motor import DefinitieCoada


class ConectorNecunoscut(LookupError):
    """Niciun conector înregistrat pentru canal."""


@dataclass(frozen=True)
class Inregistrare:
    conector: Conector
    coada: DefinitieCoada | None  # coada pe platformă, cu limita ei de rată (7.5); implicit coada `io`


_registru: dict[str, Inregistrare] = {}


def inregistreaza(canal: str, conector: Conector, *, coada: DefinitieCoada | None = None) -> None:
    """Un singur conector pe canal; a doua înregistrare îl înlocuiește (teste, reautorizare)."""
    _registru[canal] = Inregistrare(conector, coada)


# Conectorii reali de publicare (F9), încărcați la cerere doar pentru canalele din `AMA_PUBLICARE_CONECTORI`
# (implicit niciunul: în teste și în dezvoltare canalele se înregistrează explicit, pe platforme simulate).
FABRICI: dict[str, str] = {
    "facebook": "app.connectors.publicare.facebook:ConectorFacebook",
}


def _incarca(canal: str) -> Conector | None:
    from app.config import get_settings

    activi = {c.strip() for c in get_settings().publicare_conectori.split(",") if c.strip()}
    if canal not in activi or canal not in FABRICI:
        return None
    modul, clasa = FABRICI[canal].split(":")
    c = getattr(importlib.import_module(modul), clasa).din_setari()
    inregistreaza(canal, c)
    return c  # type: ignore[no-any-return]


def conector_pentru(canal: str) -> Conector:
    i = _registru.get(canal)
    if i is not None:
        return i.conector
    c = _incarca(canal)
    if c is None:
        raise ConectorNecunoscut(canal)
    return c


def coada_pentru(canal: str) -> str:
    """Numele cozii pe care rulează efectele canalului."""
    i = _registru.get(canal)
    return i.coada.nume if i is not None and i.coada is not None else "io"


def inregistrari() -> dict[str, Inregistrare]:
    return dict(_registru)


def uita_tot() -> None:
    """Golește registrul (teste)."""
    _registru.clear()


# --- efectele de sistem (F7): email, plăți; pe tip, nu pe canal ---------------------------------------------
_sistem: dict[str, ConectorSistem] = {}


def inregistreaza_sistem(tip: str, conector: ConectorSistem) -> None:
    _sistem[tip] = conector


def conector_sistem(tip: str) -> ConectorSistem:
    try:
        return _sistem[tip]
    except KeyError:
        raise ConectorNecunoscut(tip) from None


def uita_sistem() -> None:
    _sistem.clear()
