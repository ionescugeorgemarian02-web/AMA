"""Agregarea verdictelor unei rulări (9.2). Nucleu pur.

- un eșec `critica` → carantină (un om decide);
- un eșec `majora` → reparație (autorul primește instrucțiunile TUTUROR validatorilor, într-un singur
mesaj);
- fără eșec, avertismentele se adună în puncte (`minora` = 1, `majora` = 2); peste prag (STRICT) livrabilul
merge la om;
- altfel trece.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.validare.verdict import Cost, Rezultat, Severitate, Verdict

PUNCTE = {Severitate.MINORA: 1, Severitate.MAJORA: 2}


class Decizie(StrEnum):
    TRECE = "trece"
    REPARATIE = "reparatie"
    CARANTINA = "carantina"
    INTREBARE = "intrebare"  # lipsește un fapt: livrabilul se oprește cu o întrebare către client (G2, F5.3)


@dataclass(frozen=True)
class Agregat:
    decizie: Decizie
    cere_om: bool
    puncte: int
    prag: int
    blocante: tuple[Verdict, ...]
    avertismente: tuple[Verdict, ...]
    instructiune: str
    cost: Cost


def puncte_avertismente(verdicte: list[Verdict] | tuple[Verdict, ...]) -> int:
    return sum(
        PUNCTE.get(v.severitate, 0) for v in verdicte if v.rezultat is Rezultat.AVERTISMENT and v.severitate
    )


def unifica_instructiunile(blocante: tuple[Verdict, ...], avertismente: tuple[Verdict, ...]) -> str:
    """Un singur mesaj pentru autor: întâi ce blochează, apoi ce e de îmbunătățit. Instrucțiunile identice
    se
    spun o singură dată; fiecare punct își numește validatorul."""
    randuri: list[str] = []
    vazute: set[str] = set()

    def adauga(v: Verdict) -> None:
        if v.instructiune in vazute:
            return
        vazute.add(v.instructiune)
        randuri.append(f"{len(randuri) + 1}. [{v.validator}] {v.instructiune}")

    for v in blocante:
        adauga(v)
    nr_blocante = len(randuri)
    if not nr_blocante and not avertismente:
        return ""
    for v in avertismente:
        adauga(v)
    antet = (
        "Textul nu a trecut validarea. Corectează toate punctele de mai jos, fără să schimbi faptele, "
        "prețurile sau promisiunile permise:"
        if nr_blocante
        else "Textul poate fi îmbunătățit în punctele de mai jos:"
    )
    return antet + "\n" + "\n".join(randuri)


def agrega(verdicte: list[Verdict] | tuple[Verdict, ...], *, prag: int) -> Agregat:
    blocante = tuple(v for v in verdicte if v.blocheaza)
    avertismente = tuple(v for v in verdicte if v.rezultat is Rezultat.AVERTISMENT)
    puncte = puncte_avertismente(verdicte)
    cost = Cost()
    for v in verdicte:
        cost = cost + v.cost
    if any(v.critic for v in blocante):
        decizie = Decizie.CARANTINA
    elif any(v.detalii.get("intrebare") for v in blocante):
        decizie = Decizie.INTREBARE
    elif blocante:
        decizie = Decizie.REPARATIE
    else:
        decizie = Decizie.TRECE
    return Agregat(
        decizie=decizie,
        cere_om=decizie is Decizie.TRECE and puncte > prag,
        puncte=puncte,
        prag=prag,
        blocante=blocante,
        avertismente=avertismente,
        instructiune=unifica_instructiunile(blocante, avertismente),
        cost=cost,
    )
