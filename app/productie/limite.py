"""Limite anti-buclă (7.3), nucleu pur: nicio bază de date, nicio configurare citită aici.

- cel mult 2 runde de reparație per livrabil (a treia merge la om, cu diagnostic);
- cel mult 12 predări între componente (aici: intrări în stări de lucru, vezi `stari.STARI_DE_LUCRU`);
- buget per livrabil: număr maxim de apeluri LLM și timp maxim de lucru;
- întrerupătorul global: rata de eșec peste prag într-o fereastră, cu un minim de volum.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.productie.stari import STARI_DE_LUCRU, Stare


class Depasire(StrEnum):
    RUNDE_REPARATIE = "runde_reparatie"
    PREDARI = "predari"
    BUGET_APELURI = "buget_apeluri"
    BUGET_TIMP = "buget_timp"


ETICHETE: dict[Depasire, str] = {
    Depasire.RUNDE_REPARATIE: "limita de runde de reparație",
    Depasire.PREDARI: "limita de predări între componente",
    Depasire.BUGET_APELURI: "bugetul de apeluri la modele",
    Depasire.BUGET_TIMP: "bugetul de timp",
}


@dataclass(frozen=True)
class Limite:
    runde_reparatie: int = 2
    predari: int = 12


LIMITE_IMPLICITE = Limite()


def depasire_la_intrare(
    la: Stare, runde_reparatie: int, predari: int, limite: Limite = LIMITE_IMPLICITE
) -> Depasire | None:
    """Intrarea în `la` ar depăși o limită? Contoarele sunt cele de ACUM (fără intrarea aceasta)."""
    if la == Stare.IN_REPARATIE and runde_reparatie >= limite.runde_reparatie:
        return Depasire.RUNDE_REPARATIE
    if la in STARI_DE_LUCRU and predari >= limite.predari:
        return Depasire.PREDARI
    return None


def depasire_buget(apeluri: int, timp_sec: float, buget_apeluri: int, buget_timp_sec: int) -> Depasire | None:
    """Consumul a trecut peste buget? (Exact cât bugetul încă este în regulă.)"""
    if apeluri > buget_apeluri:
        return Depasire.BUGET_APELURI
    if timp_sec > buget_timp_sec:
        return Depasire.BUGET_TIMP
    return None


def rata_esec(succese: int, esecuri: int) -> float | None:
    total = succese + esecuri
    return None if total == 0 else esecuri / total


def intrerupator_declansat(succese: int, esecuri: int, prag: float, volum_min: int) -> bool:
    """Rata de eșec depășește STRICT pragul, iar volumul din fereastră e cel puțin `volum_min`: 1 eșec din 2
    nu declanșează nimic (7.3 cere minim de volum ca să nu se oprească producția pe zgomot)."""
    rata = rata_esec(succese, esecuri)
    return rata is not None and succese + esecuri >= volum_min and rata > prag
