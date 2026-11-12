"""Executorul de efecte externe (F2.5): singura ușă spre exterior (AGENTS.md, 7.3, 7.5).

    from app.operare import efecte

    # în aceeași tranzacție cu mutarea care îl justifică:
    productie.muta(db, lid, Stare.PROGRAMAT, Stare.IN_PUBLICARE, componenta="B4")
    efecte.cere(db, lid, payload={"continut_id": str(continut_id)})

Conectorii (`app.connectors`) se cheamă DOAR de aici (garda `scripts/check_efecte.py`).
"""

from app.operare.efecte.executor import (
    NUME_TIC,
    cere,
    declara_programari,
    epuizeaza_efect,
    executa,
    incearca_efect,
    porneste_executia,
    redistribuie,
    reia_conectorul,
    reia_livrabilul,
    tic,
)
from app.operare.efecte.modele import Efect, PauzaConector
from app.operare.efecte.servicii import (
    Cerere,
    EfectInexistent,
    EfectRefuzat,
    EroareEfect,
    TranzitieEfectNepermisa,
    ale_livrabilului,
    anuleaza,
    citeste,
    listeaza,
    numara_pe_stare,
    pauze,
)
from app.operare.efecte.stari import (
    ETICHETE,
    ETICHETE_TIP,
    FINALE,
    OPRIRE_PE_TIP,
    TABEL,
    Stare,
    Tip,
    cheia,
)

__all__ = [
    "ETICHETE",
    "ETICHETE_TIP",
    "FINALE",
    "NUME_TIC",
    "OPRIRE_PE_TIP",
    "TABEL",
    "Cerere",
    "Efect",
    "EfectInexistent",
    "EfectRefuzat",
    "EroareEfect",
    "PauzaConector",
    "Stare",
    "Tip",
    "TranzitieEfectNepermisa",
    "ale_livrabilului",
    "anuleaza",
    "cere",
    "cheia",
    "citeste",
    "declara_programari",
    "epuizeaza_efect",
    "executa",
    "incearca_efect",
    "listeaza",
    "numara_pe_stare",
    "pauze",
    "porneste_executia",
    "redistribuie",
    "reia_conectorul",
    "reia_livrabilul",
    "tic",
]
