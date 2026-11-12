"""Bugetul per livrabil (7.3): apeluri la modele și timp de lucru. Doar contorizarea și verificarea.

Apelurile reale la modele apar în F3 (gateway): ele vor chema `poate_consuma` înainte de un apel și
`inregistreaza_consum` după el. La depășire, livrabilul se oprește și merge la om (`tranzitii.escaleaza`).
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.productie import limite, stari
from app.productie.limite import Depasire
from app.productie.modele import Livrabil
from app.productie.stari import Stare
from app.productie.tranzitii import blocheaza, escaleaza


@dataclass(frozen=True)
class Consum:
    apeluri_llm: int
    timp_sec: float
    buget_apeluri_llm: int
    buget_timp_sec: int
    depasit: Depasire | None = None
    escaladat: bool = False
    intrare_eroare_id: uuid.UUID | None = None


def poate_consuma(livrabil: Livrabil, apeluri: int = 1, secunde: float = 0.0) -> bool:
    """Încape consumul cerut în buget? (Verificare înainte de un apel; nu scrie nimic.)"""
    return (
        limite.depasire_buget(
            livrabil.apeluri_llm + apeluri,
            livrabil.timp_sec + secunde,
            livrabil.buget_apeluri_llm,
            livrabil.buget_timp_sec,
        )
        is None
    )


def inregistreaza_consum(
    db: Session,
    livrabil_id: uuid.UUID,
    *,
    apeluri_llm: int = 0,
    secunde: float = 0.0,
    componenta: str,
    diagnostic: dict[str, Any] | None = None,
) -> Consum:
    """Adaugă consumul la livrabil (sub blocarea rândului) și îl trimite la om dacă a depășit bugetul.

    Depășirea înseamnă STRICT peste buget; consumul se înregistrează oricum (cifrele rămân adevărate).
    Un livrabil deja în coada de erori (sau în altă stare din care nu se poate escalada) nu escaladează a doua
    oară."""
    if apeluri_llm < 0 or secunde < 0:
        raise ValueError("consumul nu poate fi negativ")
    livrabil = blocheaza(db, livrabil_id)
    livrabil.apeluri_llm += apeluri_llm
    livrabil.timp_sec += secunde
    livrabil.actualizat_la = func.now()
    db.flush()
    depasit = limite.depasire_buget(
        livrabil.apeluri_llm, livrabil.timp_sec, livrabil.buget_apeluri_llm, livrabil.buget_timp_sec
    )
    if depasit is None or not stari.este_permisa(Stare(livrabil.stare), Stare.COADA_DE_ERORI):
        return Consum(
            livrabil.apeluri_llm,
            livrabil.timp_sec,
            livrabil.buget_apeluri_llm,
            livrabil.buget_timp_sec,
            depasit=depasit,
        )
    rez = escaleaza(
        db,
        livrabil,
        depasit,
        cerut=Stare.COADA_DE_ERORI,
        componenta=componenta,
        diagnostic=diagnostic,
    )
    return Consum(
        livrabil.apeluri_llm,
        livrabil.timp_sec,
        livrabil.buget_apeluri_llm,
        livrabil.buget_timp_sec,
        depasit=depasit,
        escaladat=True,
        intrare_eroare_id=rez.intrare_eroare_id,
    )
