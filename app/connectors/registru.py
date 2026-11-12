"""Registrul conectorilor de efecte, pe canal (F2.5). Se importă DOAR din executor și din conectori
(garda `scripts/check_efecte.py`): restul aplicației cere efecte prin `app.operare.efecte.cere`."""

from dataclasses import dataclass

from app.connectors.contract import Conector
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


def conector_pentru(canal: str) -> Conector:
    try:
        return _registru[canal].conector
    except KeyError:
        raise ConectorNecunoscut(canal) from None


def coada_pentru(canal: str) -> str:
    """Numele cozii pe care rulează efectele canalului."""
    i = _registru.get(canal)
    return i.coada.nume if i is not None and i.coada is not None else "io"


def inregistrari() -> dict[str, Inregistrare]:
    return dict(_registru)


def uita_tot() -> None:
    """Golește registrul (teste)."""
    _registru.clear()
