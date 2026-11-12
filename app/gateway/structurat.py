"""Apelul structurat cu validare și o singură reparație (8.6, 7.5: „ieșire în afara schemei → o reparație,
apoi alt
model”). Nucleu fără rețea: cererea HTTP este o funcție dată, deci se testează cu răspunsuri fabricate."""

from collections.abc import Callable
from dataclasses import dataclass, field

from app.gateway.iesire import Iesire, cerere_reparatie, cu_instructiune, schema_json, valideaza
from app.gateway.tipuri import Mesaj, RaspunsModel


@dataclass(frozen=True)
class IesireStructurata:
    obiect: Iesire
    raspunsuri: tuple[RaspunsModel, ...]  # 1 sau 2 (cu reparație)
    reparat: bool
    eroare_initiala: str = ""  # de ce a fost nevoie de reparație (câmpuri, fără valori)

    @property
    def tokeni_intrare(self) -> int:
        return sum(r.tokeni_intrare for r in self.raspunsuri)

    @property
    def tokeni_iesire(self) -> int:
        return sum(r.tokeni_iesire for r in self.raspunsuri)


class IesireNevalida(Exception):
    """Răspunsul rămâne în afara schemei și după reparație. Poartă răspunsurile (tokenii se contorizează
    oricum)."""

    def __init__(self, eroare: str, raspunsuri: tuple[RaspunsModel, ...]) -> None:
        super().__init__(eroare)
        self.eroare = eroare
        self.raspunsuri = raspunsuri


@dataclass
class _Stare:
    raspunsuri: list[RaspunsModel] = field(default_factory=list)


def ruleaza_structurat(
    trimite: Callable[[tuple[Mesaj, ...]], RaspunsModel],
    mesaje: tuple[Mesaj, ...],
    schema: type[Iesire],
    *,
    nativ: bool,
) -> IesireStructurata:
    """`nativ`: furnizorul primește schema în cerere (`trimite` o pune); altfel schema intră în
    instrucțiuni."""
    de_trimis = mesaje if nativ else cu_instructiune(mesaje, schema_json(schema))
    stare = _Stare()
    primul = trimite(de_trimis)
    stare.raspunsuri.append(primul)
    verdict = valideaza(primul.text, schema)
    if verdict.obiect is not None:
        return IesireStructurata(verdict.obiect, tuple(stare.raspunsuri), reparat=False)
    eroare_initiala = verdict.eroare
    al_doilea = trimite(cerere_reparatie(de_trimis, primul.text, eroare_initiala))
    stare.raspunsuri.append(al_doilea)
    verdict = valideaza(al_doilea.text, schema)
    if verdict.obiect is not None:
        return IesireStructurata(
            verdict.obiect, tuple(stare.raspunsuri), reparat=True, eroare_initiala=eroare_initiala
        )
    raise IesireNevalida(verdict.eroare, tuple(stare.raspunsuri))
