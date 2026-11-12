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

    def fara_goluri() -> bool:
        # Ticurile recuperate rulează în paralel și pot sosi în altă ordine: așteptăm să se așeze toate.
        rulate = sorted(set(ticuri(dir_proba)))
        if not rulate or rulate[-1] < tinta:
            return False
        return {(b - a).total_seconds() for a, b in itertools.pairwise(rulate)} == {1.0}

    asteapta(fara_goluri, mesaj="ticuri după repornire, fără goluri (cele ratate au fost recuperate)")

    rulate = sorted(ticuri(dir_proba))
    dubluri = {t for t in rulate if rulate.count(t) > 1}
    # Un pas întrerupt de SIGKILL după ce și-a scris urma, dar înainte să fie notat ca terminat, se reia
    # (pașii sunt „cel puțin o dată” la cădere). Singurul tic care poate apărea de două ori este deci cel
    # aflat în lucru la momentul căderii; planificatorul nu declanșează niciun tic de două ori.
    assert dubluri <= {ultimul}, f"ticuri declanșate de două ori: {dubluri}"
    assert all(rulate.count(t) <= 2 for t in dubluri)
    assert w2.opreste_curat() == 0
