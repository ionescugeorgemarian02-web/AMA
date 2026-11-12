"""Fluxuri de probă pentru testele de avarie. Se încarcă în procesul worker prin `AMA_WORKER_MODULE_TEST`.

Coordonarea cu testul se face prin fișiere în `AMA_PROBA_DIR` (adăugare de linii = „s-a întâmplat”): nu depinde de
ceas sau de pauze, iar numărarea liniilor arată câte ori a rulat fiecare pas.
"""

import os
import time
from pathlib import Path

from app.operare import motor


def director() -> Path:
    return Path(os.environ["AMA_PROBA_DIR"])


def noteaza(nume: str) -> None:
    with (director() / nume).open("a", encoding="utf-8") as f:
        f.write("x\n")
        f.flush()
        os.fsync(f.fileno())


def numara(nume: str) -> int:
    p = director() / nume
    return len(p.read_text(encoding="utf-8").splitlines()) if p.exists() else 0


def asteapta_fisier_disparut(nume: str) -> None:
    while (director() / nume).exists():
        time.sleep(0.02)


@motor.pas("proba.pas1")
def pas1(job: str) -> str:
    noteaza(f"{job}.pas1")
    return "p1"


@motor.pas("proba.pas2")
def pas2(job: str) -> str:
    noteaza(f"{job}.pas2.inceput")
    asteapta_fisier_disparut(f"{job}.blocheaza")  # cât există fișierul, pasul stă (testul îl omoară aici)
    noteaza(f"{job}.pas2.sfarsit")
    return "p2"


@motor.pas("proba.pas3")
def pas3(job: str) -> str:
    noteaza(f"{job}.pas3")
    return "p3"


@motor.flux("proba.trei_pasi")
def trei_pasi(job: str) -> str:
    noteaza(f"{job}.flux")  # corpul fluxului se reexecută la reluare; pașii salvați nu
    a, b, c = pas1(job), pas2(job), pas3(job)
    noteaza(f"{job}.terminat")
    return a + b + c


@motor.flux("proba.simplu")
def simplu(job: str) -> str:
    noteaza(f"{job}.simplu")
    return "gata"


@motor.pas("proba.instabil", reincercari=3, pauza_sec=0.05, factor=1.0)
def instabil(job: str) -> str:
    noteaza(f"{job}.incercare")
    if numara(f"{job}.incercare") < 3:
        raise motor.EroareTemporara("încă nu")
    return "ok"


@motor.flux("proba.cu_reincercari")
def cu_reincercari(job: str) -> str:
    return instabil(job)


@motor.pas("proba.definitiv")
def definitiv(job: str) -> str:
    noteaza(f"{job}.incercare")
    raise motor.EroareDefinitiva("nu are sens")


@motor.flux("proba.cu_eroare_definitiva")
def cu_eroare_definitiva(job: str) -> str:
    return definitiv(job)


@motor.pas("proba.mereu_temporar", reincercari=2, pauza_sec=0.05, factor=1.0)
def mereu_temporar(job: str) -> str:
    noteaza(f"{job}.incercare")
    raise motor.EroareTemporara("mereu")


@motor.flux("proba.cu_reincercari_epuizate")
def cu_reincercari_epuizate(job: str) -> str:
    return mereu_temporar(job)


@motor.pas("proba.continut")
def pas_cu_continut(corp: str) -> str:
    return corp


@motor.flux("proba.cu_continut_in_pas")
def cu_continut_in_pas(job: str) -> str:
    return pas_cu_continut("conținut lung " * 40)
