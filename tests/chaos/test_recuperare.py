"""F2.1 — „Gata când”: un flux de probă oprit la mijloc reia de la ultimul pas după repornire.

Workeri reali (subprocese), Postgres real. Workerul este omorât cu SIGKILL în mijlocul pasului 2; un al doilea
proces, cu același `AMA_WORKER_ID`, preia jobul. Pasul 1 (deja salvat) nu se mai execută; pasul 2 (întrerupt) se
reia; pasul 3 și încheierea se întâmplă exact o dată.
"""

from pathlib import Path

from app.operare import motor
from tests.chaos import fluxuri_proba as proba
from tests.chaos.utile import Worker, asteapta
from tests.conftest import BazaTest


def numar(dir_proba: Path, nume: str) -> int:
    p = dir_proba / nume
    return len(p.read_text().splitlines()) if p.exists() else 0


def test_flux_oprit_la_mijloc_reia_de_la_ultimul_pas(
    baza: BazaTest, dir_proba: Path, workeri: list[Worker]
) -> None:
    (dir_proba / "j1.blocheaza").touch()
    w1 = Worker(baza, dir_proba).porneste()
    workeri.append(w1)
    w1.asteapta_pornit()

    job = motor.trimite(proba.trei_pasi, "j1", cheie="chaos-j1")
    asteapta(lambda: numar(dir_proba, "j1.pas2.inceput") == 1, mesaj="începutul pasului 2")
    w1.omoara()  # SIGKILL în mijlocul pasului 2

    stare = motor.stare_flux(job)
    assert stare is not None and stare.stare is motor.StareJob.IN_LUCRU, (
        "jobul nu trebuie pierdut sau dat drept terminat"
    )
    assert numar(dir_proba, "j1.pas2.sfarsit") == 0

    (dir_proba / "j1.blocheaza").unlink()  # al doilea proces nu mai blochează
    w2 = Worker(baza, dir_proba).porneste()  # aceeași identitate ca primul, ca la repornirea din compose
    workeri.append(w2)
    final = motor.asteapta_flux(job, timeout_sec=30)

    assert final.stare is motor.StareJob.TERMINAT
    assert numar(dir_proba, "j1.pas1") == 1, "pasul salvat nu se reexecută"
    assert numar(dir_proba, "j1.pas2.inceput") == 2, "pasul întrerupt se reia"
    assert numar(dir_proba, "j1.pas2.sfarsit") == 1
    assert numar(dir_proba, "j1.pas3") == 1
    assert numar(dir_proba, "j1.terminat") == 1, "jobul se termină exact o dată"
    assert numar(dir_proba, "j1.flux") == 2, "corpul fluxului se reexecută (pașii nu)"
    assert w2.opreste_curat() == 0


def test_oprirea_curata_la_sigterm_iese_cu_zero_si_nu_pierde_jobul_in_lucru(
    baza: BazaTest, dir_proba: Path, workeri: list[Worker]
) -> None:
    (dir_proba / "j2.blocheaza").touch()
    w1 = Worker(baza, dir_proba, **{"AMA_WORKER_OPRIRE_SEC": "1"}).porneste()
    workeri.append(w1)
    w1.asteapta_pornit()
    job = motor.trimite(proba.trei_pasi, "j2", cheie="chaos-j2")
    asteapta(lambda: numar(dir_proba, "j2.pas2.inceput") == 1, mesaj="începutul pasului 2")

    assert w1.opreste_curat() == 0, w1.text()  # SIGTERM cu un job care nu se termină în fereastra de oprire
    assert "worker oprit curat" in w1.text()
    stare = motor.stare_flux(job)
    assert stare is not None and not stare.stare.final, (
        "jobul rămas în lucru nu trebuie marcat terminat sau eșuat"
    )

    (dir_proba / "j2.blocheaza").unlink()
    w2 = Worker(baza, dir_proba).porneste()
    workeri.append(w2)
    assert motor.asteapta_flux(job, timeout_sec=30).stare is motor.StareJob.TERMINAT
    assert numar(dir_proba, "j2.terminat") == 1
    assert w2.opreste_curat() == 0
