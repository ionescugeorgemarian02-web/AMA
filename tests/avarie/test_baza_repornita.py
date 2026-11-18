"""F15.1, docs/25 §25.3: baza de date repornește în mijlocul unui workflow -> reia de la ultimul pas, fără
efecte duble.

Repornirea bazei e simulată prin închiderea forțată a TUTUROR conexiunilor spre baza de test
(`pg_terminate_backend`) ale aplicației, exact ce vede ea când Postgres repornește (conexiunile de
administrare ale testului rămân, ca să poată curăța la final). Workerul e un proces real, sub un
supervizor (`restart: unless-stopped`); dacă moare din cauza conexiunilor pierdute, e repornit.
"""

import time
from pathlib import Path

import psycopg
import pytest

from app.operare import motor
from tests.chaos import fluxuri_proba as proba
from tests.chaos.utile import Supervizor, Worker, asteapta
from tests.conftest import BazaTest, _psycopg_dsn

pytestmark = pytest.mark.db


def _numar(d: Path, nume: str) -> int:
    p = d / nume
    return len(p.read_text().splitlines()) if p.exists() else 0


def _reporneste_baza(baza: BazaTest) -> int:
    with psycopg.connect(_psycopg_dsn(baza.admin_url), autocommit=True) as c:
        rows = c.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND usename <> current_user",
            (baza.nume,),
        ).fetchall()
    return len(rows)


def _asteapta_terminat(job: str) -> motor.StareFlux:
    for _ in range(30):
        try:
            return motor.asteapta_flux(job, timeout_sec=30)
        except Exception:  # conexiunea procesului de test a căzut și ea; se reface la următoarea încercare
            time.sleep(0.5)
    raise AssertionError("fluxul nu s-a terminat după repornirea bazei")


def test_baza_repornita_la_mijloc_fluxul_reia_fara_pasi_dubli(
    baza: BazaTest, dir_proba: Path, workeri: list[Worker]
) -> None:
    (dir_proba / "b1.blocheaza").touch()
    w = Worker(baza, dir_proba)
    workeri.append(w)
    sup = Supervizor(w).porneste()
    try:
        w.asteapta_pornit()
        job = motor.trimite(proba.trei_pasi, "b1", cheie="avarie-baza-b1")
        asteapta(lambda: _numar(dir_proba, "b1.pas2.inceput") >= 1, mesaj="începutul pasului 2")
        assert _reporneste_baza(baza) >= 1, "nicio conexiune închisă: simularea n-a atins workerul"
        (dir_proba / "b1.blocheaza").unlink()
        final = _asteapta_terminat(job)
        assert final.stare is motor.StareJob.TERMINAT
        assert _numar(dir_proba, "b1.pas1") == 1, "pasul salvat înainte de repornire nu se reexecută"
        assert _numar(dir_proba, "b1.pas3") == 1 and _numar(dir_proba, "b1.terminat") == 1, (
            "fără efecte duble"
        )
    finally:
        sup.curata()
