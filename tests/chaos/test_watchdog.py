"""F2.7 — „Gata când”: un worker oprit forțat este repornit și jobul lui se reia.

Procese reale (SIGKILL) și un supervizor care ține locul politicii de restart din compose. Al doilea test este
cazul rău: un job care strică workerul de fiecare dată (o „pastilă otrăvită”) nu trebuie să țină sistemul într-o
buclă infinită — după căderile permise ajunge în coada de erori, iar repornirile repetate se anunță.
"""

from pathlib import Path

from sqlalchemy import Engine, text

from app.operare import motor
from tests.chaos import fluxuri_proba as proba
from tests.chaos.utile import Supervizor, Worker, asteapta
from tests.conftest import BazaTest

MEDIU = {
    "AMA_WATCHDOG_BATAIE_SEC": "0.3",
    "AMA_WATCHDOG_SCANARE_SEC": "0.5",
    "AMA_WORKER_TIMEOUT_SEC": "5",
}


def numar(dir_proba: Path, nume: str) -> int:
    p = dir_proba / nume
    return len(p.read_text().splitlines()) if p.exists() else 0


def evenimente(admin: Engine, tip: str) -> int:
    with admin.connect() as c:
        return int(
            c.execute(text("SELECT count(*) FROM worker_evenimente WHERE tip = :t"), {"t": tip}).scalar_one()
        )


def test_worker_oprit_fortat_este_repornit_si_jobul_se_termina_exact_o_data(
    baza: BazaTest, dir_proba: Path, workeri: list[Worker], admin_engine: Engine
) -> None:
    with admin_engine.begin() as c:
        c.execute(text("TRUNCATE worker_semnale, worker_evenimente, coada_erori"))
    (dir_proba / "w1.blocheaza").touch()
    worker = Worker(baza, dir_proba, **MEDIU)
    supervizor = Supervizor(worker)
    workeri.append(worker)
    supervizor.porneste()
    worker.asteapta_pornit()

    assert worker.verificare_sanatate() == 0, "verificarea de sănătate din compose: workerul trăiește"
    job = motor.trimite(proba.trei_pasi, "w1", cheie="chaos-wd-w1")
    asteapta(lambda: numar(dir_proba, "w1.pas2.inceput") == 1, mesaj="începutul pasului 2")
    pid_vechi = worker.proces.pid  # type: ignore[union-attr]
    worker.omoara()  # SIGKILL în mijlocul pasului 2
    (dir_proba / "w1.blocheaza").unlink()  # procesul repornit nu mai blochează

    final = motor.asteapta_flux(job, timeout_sec=30)
    assert final.stare is motor.StareJob.TERMINAT
    assert supervizor.reporniri == 1 and worker.proces.pid != pid_vechi  # type: ignore[union-attr]
    assert numar(dir_proba, "w1.pas1") == 1, "pasul salvat nu se repetă"
    assert numar(dir_proba, "w1.pas2.inceput") == 2 and numar(dir_proba, "w1.pas2.sfarsit") == 1
    assert numar(dir_proba, "w1.pas3") == 1 and numar(dir_proba, "w1.terminat") == 1, (
        "jobul se termină exact o dată"
    )

    # watchdog-ul a văzut căderea: o repornire după cădere, sub pragul de alertă (3)
    asteapta(lambda: evenimente(admin_engine, "repornit_dupa_cadere") == 1, mesaj="căderea înregistrată")
    assert evenimente(admin_engine, "alerta_reporniri") == 0
    with admin_engine.connect() as c:
        rand = c.execute(
            text("SELECT pid, oprit_curat, ultimul_semnal > now() - interval '5 seconds' FROM worker_semnale")
        ).one()
    assert rand[0] == worker.proces.pid and rand[1] is False and rand[2] is True, "workerul nou bate"
    assert supervizor.opreste() == 0
    with admin_engine.connect() as c:
        assert c.execute(text("SELECT oprit_curat FROM worker_semnale")).scalar_one() is True
    assert worker.verificare_sanatate() == 1, "un worker oprit nu e „sănătos”"


def test_un_job_care_strica_workerul_de_fiecare_data_ajunge_in_coada_de_erori_si_anunta_reporniri(
    baza: BazaTest, dir_proba: Path, workeri: list[Worker], admin_engine: Engine
) -> None:
    with admin_engine.begin() as c:
        c.execute(text("TRUNCATE worker_semnale, worker_evenimente, coada_erori"))
    worker = Worker(baza, dir_proba, **MEDIU, AMA_WATCHDOG_PRAG_REPORNIRI="2")
    supervizor = Supervizor(worker)
    workeri.append(worker)
    supervizor.porneste()
    worker.asteapta_pornit()

    job = motor.trimite(proba.otravit, "p1", cheie="chaos-wd-p1")
    final = motor.asteapta_flux(job, timeout_sec=45)
    assert final.stare is motor.StareJob.EPUIZAT, "după căderile permise jobul nu mai este reluat"
    assert numar(dir_proba, "p1.otrava") == 2, "o rulare inițială și o recuperare, apoi s-a oprit"

    def intrare() -> list[tuple[str, str, str, str | None]]:
        with admin_engine.connect() as c:
            return [
                tuple(r)
                for r in c.execute(
                    text(
                        "SELECT stare_job, severitate, stare, pas FROM coada_erori WHERE workflow_id = 'chaos-wd-p1'"
                    )
                )
            ]

    asteapta(lambda: bool(intrare()), timeout_sec=20, mesaj="intrarea în coada de erori")
    assert intrare() == [("epuizat", "major", "noua", None)]
    with admin_engine.connect() as c:
        context = c.execute(
            text("SELECT context FROM coada_erori WHERE workflow_id = 'chaos-wd-p1'")
        ).scalar_one()
    assert context["flux"] == "proba.otravit" and context["argumente"] == ["p1"]
    assert any("reluat de" in x and "căderi ale workerului" in x for x in context["ce_s_a_incercat"])

    assert evenimente(admin_engine, "repornit_dupa_cadere") >= 2
    assert evenimente(admin_engine, "alerta_reporniri") == 1, "repornirile repetate se anunță o singură dată"
    assert supervizor.opreste() == 0
