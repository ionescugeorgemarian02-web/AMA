"""F2.6 — programarea supraviețuiește căderii workerului: după SIGKILL și repornire, ticurile ratate se recuperă.

Cron de o secundă (ceas real, fără pauze lungi). Fiecare tic rulează exact o dată și nu rămâne niciun gol între
primul și ultimul tic, deși workerul a lipsit câteva secunde.
"""

import datetime as dt
import itertools
from pathlib import Path

from tests.chaos.utile import Worker, asteapta
from tests.conftest import BazaTest


def ticuri(dir_proba: Path) -> list[dt.datetime]:
    p = dir_proba / "tic.log"
    return [dt.datetime.fromisoformat(r) for r in p.read_text().split()] if p.exists() else []


def test_dupa_sigkill_nu_raman_goluri_si_nu_exista_dubluri(
    baza: BazaTest, dir_proba: Path, workeri: list[Worker]
) -> None:
    mediu = {"AMA_PROBA_PROGRAMARE": "1", "AMA_PROGRAMARE_POLLING_SEC": "0.3"}
    w1 = Worker(baza, dir_proba, **mediu).porneste()
    workeri.append(w1)
    asteapta(lambda: len(ticuri(dir_proba)) >= 2, mesaj="primele ticuri")
    w1.omoara()
    inainte = len(ticuri(dir_proba))
    ultimul = max(ticuri(dir_proba))

    asteapta(lambda: dt.datetime.now(dt.UTC) > ultimul + dt.timedelta(seconds=2), mesaj="trecerea golului")
    assert len(ticuri(dir_proba)) == inainte, "cât workerul lipsește nu se execută nimic"

    w2 = Worker(baza, dir_proba, **mediu).porneste()
    workeri.append(w2)
    tinta = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=1)
    asteapta(
        lambda: bool(ticuri(dir_proba)) and max(ticuri(dir_proba)) >= tinta, mesaj="ticuri după repornire"
    )

    rulate = sorted(ticuri(dir_proba))
    assert len(rulate) == len(set(rulate)), "niciun tic nu rulează de două ori"
    pasi = {(b - a).total_seconds() for a, b in itertools.pairwise(rulate)}
    assert pasi == {1.0}, f"ticurile din intervalul în care workerul a lipsit au fost recuperate: {pasi}"
    assert w2.opreste_curat() == 0
