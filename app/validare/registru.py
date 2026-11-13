"""Registrul validatorilor (9.4): DATE (cod G, nume, versiune, treaptă, ordine, tipuri și canale la care se
aplică) plus
implementarea înregistrată cu decoratorul. Un validator cu mai multe trepte (G2: V1 și V3) are câte un pas
pe treaptă.

    @registru.validator(DefinitieValidator("G1", "Structură", "1", Treapta.V0))
    def g1(intrare: Intrare) -> Verdict | list[Verdict] | None: ...

O implementare întoarce un verdict, mai multe, sau `None` (nu se aplică acestui livrabil: nu produce
verdict).
"""

import contextlib
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass

from app.validare.intrare import Intrare
from app.validare.verdict import Treapta, Verdict

Implementare = Callable[[Intrare], Verdict | Sequence[Verdict] | None]


@dataclass(frozen=True)
class DefinitieValidator:
    cod: str  # „G1”
    nume: str
    versiune: str
    treapta: Treapta
    ordine: int = 100  # în cadrul treptei (mai mic = mai devreme)
    tipuri: frozenset[str] | None = None  # None = toate tipurile de livrabil
    canale: frozenset[str] | None = None  # None = toate canalele
    foloseste_model: bool = False  # V3 / V4: opțional, cere `judecatori` / `v4`
    descriere: str = ""

    def se_aplica(self, tip: str, canal: str) -> bool:
        return (self.tipuri is None or tip in self.tipuri) and (self.canale is None or canal in self.canale)


@dataclass(frozen=True)
class Pas:
    definitie: DefinitieValidator
    implementare: Implementare

    @property
    def cheie(self) -> tuple[str, Treapta]:
        return (self.definitie.cod, self.definitie.treapta)


_REGISTRU: dict[tuple[str, Treapta], Pas] = {}


class RegistruInvalid(ValueError):
    pass


def inregistreaza(definitie: DefinitieValidator, implementare: Implementare) -> None:
    if definitie.treapta is Treapta.V5:
        raise RegistruInvalid("V5 este omul: nu are implementare automată")
    if definitie.foloseste_model and definitie.treapta.ordine < 3:
        raise RegistruInvalid("un validator cu model e cel puțin V3")
    if not definitie.foloseste_model and definitie.treapta.ordine >= 3:
        raise RegistruInvalid("treptele V3 și V4 folosesc un model")
    _REGISTRU[(definitie.cod, definitie.treapta)] = Pas(definitie, implementare)


def validator(definitie: DefinitieValidator) -> Callable[[Implementare], Implementare]:
    def decor(f: Implementare) -> Implementare:
        inregistreaza(definitie, f)
        return f

    return decor


def sterge(cod: str, treapta: Treapta | None = None) -> None:
    for cheie in [k for k in _REGISTRU if k[0] == cod and (treapta is None or k[1] == treapta)]:
        del _REGISTRU[cheie]


def toate() -> list[DefinitieValidator]:
    return [p.definitie for p in sorted(_REGISTRU.values(), key=_ordine)]


def _ordine(p: Pas) -> tuple[int, int, str]:
    return (p.definitie.treapta.ordine, p.definitie.ordine, p.definitie.cod)


def pasi_pentru(tip: str, canal: str, *, judecatori: bool = False, v4: bool = False) -> list[Pas]:
    """Pașii care se aplică unui livrabil, în ordinea cascadei (treaptă, ordine, cod)."""
    iesire = []
    for p in sorted(_REGISTRU.values(), key=_ordine):
        d = p.definitie
        if not d.se_aplica(tip, canal):
            continue
        if d.foloseste_model and not (v4 if d.treapta is Treapta.V4 else judecatori):
            continue
        iesire.append(p)
    return iesire


@contextlib.contextmanager
def izolat(pastreaza: Iterable[str] = ()) -> Iterator[None]:
    """Un registru restrâns pe durata blocului: gol, sau doar cu validatorii cu codurile din `pastreaza`
    (testele unui
    validator nu vor ceilalți validatori reali). La final revine registrul de dinainte."""
    salvat = dict(_REGISTRU)
    pastrate = set(pastreaza)
    _REGISTRU.clear()
    _REGISTRU.update({k: p for k, p in salvat.items() if k[0] in pastrate})
    try:
        yield
    finally:
        _REGISTRU.clear()
        _REGISTRU.update(salvat)
