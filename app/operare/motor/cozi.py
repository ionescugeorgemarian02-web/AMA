"""Cozile din 7.5 și prioritățile P0–P3. Modul pur: nu atinge biblioteca, deci se testează fără bază.

Biblioteca ordonează joburile dintr-o coadă după `priority` (număr mai mic = mai întâi) și, la egalitate,
după momentul intrării în coadă. Nu are „termen” ca noțiune. Ca „în aceeași prioritate să câștige termenul cel
mai apropiat” să funcționeze cât permite ea, numărul de prioritate codifică ambele:

    prioritate_bibliotecă = 1 + clasa × 10^8 + minutele de la 2026-01-01 până la termen (plafonate)

Limite spuse deschis: ordinea se stabilește la intrarea în coadă (un job nu e „promovat” pe măsură ce termenul
se apropie), granulația termenului este un minut, iar un job care a început deja nu este oprit pentru unul mai
urgent. Joburile fără termen vin după cele cu termen din aceeași clasă.
"""

import datetime as dt
import re
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from app.config import Settings

EPOCA = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
PAS_CLASA = 10**8  # minute: ~190 de ani de termene într-o clasă
MAX_BIBLIOTECA = 2**31 - 1


class Coada(StrEnum):
    URGENT = "urgent"  # opriri, alerte, corecturi: fără așteptare
    GREU = "greu"  # randare, voce, transcriere, OCR, generare locală: câte un job pe culoar
    IO = "io"  # conectori, crawl, email
    INVATARE = "invatare"  # optimizări, evaluări, consolidarea memoriei


class Prioritate(IntEnum):
    P0 = 0  # termen de client în următoarele 24 de ore
    P1 = 1  # producția programată
    P2 = 2  # cercetare și raportare
    P3 = 3  # învățare


def calculeaza_prioritate(prioritate: Prioritate, termen: dt.datetime | None = None) -> int:
    """Numărul trimis bibliotecii (1 … 2^31-1). Mai mic înseamnă mai devreme."""
    if termen is None:
        minute = PAS_CLASA - 1
    else:
        if termen.tzinfo is None:
            raise ValueError("termenul trebuie să aibă fus orar (UTC)")
        minute = int((termen - EPOCA).total_seconds() // 60)
        minute = max(0, min(minute, PAS_CLASA - 1))
    valoare = 1 + int(prioritate) * PAS_CLASA + minute
    if (
        not 1 <= valoare <= MAX_BIBLIOTECA
    ):  # imposibil cu constantele de mai sus; păzește o modificare greșită
        raise ValueError("prioritate în afara intervalului bibliotecii")
    return valoare


NUME_COADA = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


@dataclass(frozen=True)
class DefinitieCoada:
    nume: str
    paralel_global: int | None = None  # câte joburi ale cozii rulează simultan, în tot sistemul
    paralel_worker: int | None = None  # ... pe un singur worker
    cereri: int | None = None  # limita de rată: cel mult `cereri` porniri pe `perioada_sec`
    perioada_sec: float | None = None
    polling_sec: float = 1.0

    def __post_init__(self) -> None:
        if not NUME_COADA.match(self.nume):
            raise ValueError(f"nume de coadă nepermis: {self.nume!r}")
        if (self.cereri is None) != (self.perioada_sec is None):
            raise ValueError("limita de rată cere și `cereri`, și `perioada_sec`")
        if self.cereri is not None and self.cereri < 1:
            raise ValueError("`cereri` trebuie să fie ≥ 1")
        if self.perioada_sec is not None and self.perioada_sec <= 0:
            raise ValueError("`perioada_sec` trebuie să fie > 0")


def nume_coada_furnizor(furnizor: str) -> str:
    """O coadă pe furnizor de modele (7.5). Furnizorii concreți apar în F3; aici doar fabrica."""
    return f"furnizor_{furnizor}"


def nume_coada_platforma(platforma: str) -> str:
    """O coadă pe platformă (limita de rată a conectorului), pentru intrări și ieșiri. Conectorii: F9."""
    return f"platforma_{platforma}"


def coada_furnizor(
    furnizor: str, *, cereri: int, perioada_sec: float, paralel: int | None = None
) -> DefinitieCoada:
    return DefinitieCoada(
        nume_coada_furnizor(furnizor), paralel_global=paralel, cereri=cereri, perioada_sec=perioada_sec
    )


def coada_platforma(
    platforma: str, *, cereri: int, perioada_sec: float, paralel: int | None = None
) -> DefinitieCoada:
    return DefinitieCoada(
        nume_coada_platforma(platforma), paralel_global=paralel, cereri=cereri, perioada_sec=perioada_sec
    )


def definitii_standard(s: Settings) -> list[DefinitieCoada]:
    """Cele patru cozi fixe din 7.5, cu limitele din configurare."""
    p = s.motor_polling_sec
    return [
        # Fără așteptare: nicio limită, sondare mai deasă.
        DefinitieCoada(Coada.URGENT.value, polling_sec=min(p, 0.5)),
        # Câte un job pe culoar: numărul de culoare = numărul de joburi simultane (2 la 8 nuclee).
        DefinitieCoada(
            Coada.GREU.value, paralel_global=s.culoare_greu, paralel_worker=s.culoare_greu, polling_sec=p
        ),
        DefinitieCoada(
            Coada.IO.value, paralel_global=s.io_paralel, paralel_worker=s.io_paralel, polling_sec=p
        ),
        DefinitieCoada(
            Coada.INVATARE.value,
            paralel_global=s.invatare_paralel,
            paralel_worker=s.invatare_paralel,
            polling_sec=p,
        ),
    ]
