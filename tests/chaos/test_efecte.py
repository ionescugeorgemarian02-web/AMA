"""F2.5 — teste de avarie ale executorului de efecte (25.3: „Platforma răspunde cu eroare după ce a publicat”,
„Baza de date repornește în mijlocul unui workflow … fără efecte duble”). Workeri reali, SIGKILL, Postgres real;
„platforma” este conectorul fals (SIMULAT), cu starea în fișiere, ca să supraviețuiască procesului omorât."""

import threading
import uuid
from pathlib import Path

import pytest

from app.connectors import registru
from app.db import sesiune_tenant
from app.operare import efecte
from tests.chaos.utile import Worker, asteapta
from tests.conector_fals import ConectorFals
from tests.conftest import BazaTest
from tests.integration.utile_productie import livrabil_in_publicare, stare

pytestmark = pytest.mark.db
MODUL = {"AMA_WORKER_MODULE_TEST": "tests.chaos.fluxuri_efecte"}


@pytest.fixture
def platforma(dir_proba: Path) -> ConectorFals:
    registru.uita_tot()
    fals = ConectorFals(dir_proba)
    registru.inregistreaza("fals", fals)
    yield fals  # type: ignore[misc]
    registru.uita_tot()


def stare_efect(tenant: uuid.UUID, efect_id: uuid.UUID) -> str:
    with sesiune_tenant(tenant) as db:
        e = efecte.citeste(db, efect_id)
        assert e is not None
        return e.stare


def cere(tenant: uuid.UUID, lid: uuid.UUID) -> efecte.Cerere:
    with sesiune_tenant(tenant) as db:
        return efecte.cere(db, lid)  # pune și jobul în coadă, după commit


def test_sigkill_inainte_de_trimitere_efectul_exista_o_data_dupa_repornire(
    baza: BazaTest,
    dir_proba: Path,
    workeri: list[Worker],
    platforma: ConectorFals,
    tenant: uuid.UUID,
    om: uuid.UUID,
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    platforma.scenariu(trimite=["blocheaza_inainte"])
    (platforma.dir / "blocheaza").touch()
    w1 = Worker(baza, dir_proba, **MODUL).porneste()
    workeri.append(w1)
    w1.asteapta_pornit()

    e = cere(tenant, lid).efect
    asteapta(lambda: (platforma.dir / "inainte.marcaj").exists(), mesaj="începutul trimiterii")
    w1.omoara()  # SIGKILL: încercarea a început, nimic nu a ajuns încă la platformă
    assert platforma.postari() == []
    assert stare_efect(tenant, e.id) == "in_trimitere", "rezultat necunoscut, nu pierdut"

    (platforma.dir / "blocheaza").unlink()
    w2 = Worker(baza, dir_proba, **MODUL).porneste()
    workeri.append(w2)
    asteapta(
        lambda: stare_efect(tenant, e.id) == "trimis", timeout_sec=60, mesaj="efectul trimis după repornire"
    )

    assert len(platforma.postari(e.cheia)) == 1, "exact o dată la platformă"
    assert [a.split()[0] for a in platforma.apeluri()] == ["trimite", "verifica", "trimite"], (
        "după o cădere, executorul întreabă platforma înainte de a retrimite"
    )
    assert stare(tenant, lid).value == "publicat"
    assert w2.opreste_curat() == 0


def test_sigkill_dupa_ce_platforma_a_inregistrat_trimiterea_nu_se_retrimite(
    baza: BazaTest,
    dir_proba: Path,
    workeri: list[Worker],
    platforma: ConectorFals,
    tenant: uuid.UUID,
    om: uuid.UUID,
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    platforma.scenariu(trimite=["blocheaza_dupa"])
    (platforma.dir / "blocheaza").touch()
    w1 = Worker(baza, dir_proba, **MODUL).porneste()
    workeri.append(w1)
    w1.asteapta_pornit()

    e = cere(tenant, lid).efect
    asteapta(lambda: (platforma.dir / "dupa.marcaj").exists(), mesaj="postarea la platformă")
    w1.omoara()  # SIGKILL: platforma are postarea, executorul nu a apucat să noteze rezultatul
    assert len(platforma.postari()) == 1
    assert stare_efect(tenant, e.id) == "in_trimitere"
    assert stare(tenant, lid).value == "in_publicare"

    (platforma.dir / "blocheaza").unlink()
    w2 = Worker(baza, dir_proba, **MODUL).porneste()
    workeri.append(w2)
    asteapta(
        lambda: stare_efect(tenant, e.id) == "trimis", timeout_sec=60, mesaj="efectul notat după repornire"
    )

    assert len(platforma.postari(e.cheia)) == 1, "exact o dată la platformă"
    assert [a.split()[0] for a in platforma.apeluri()] == ["trimite", "verifica"], (
        "doar verificare, fără retrimitere"
    )
    with sesiune_tenant(tenant) as db:
        final = efecte.citeste(db, e.id)
        assert final is not None and final.id_extern == platforma.postari()[0]["id"]
    assert stare(tenant, lid).value == "publicat"
    assert w2.opreste_curat() == 0


def test_doua_cereri_concurente_cu_aceeasi_cheie_un_singur_rand_o_singura_trimitere(
    baza: BazaTest,
    dir_proba: Path,
    workeri: list[Worker],
    platforma: ConectorFals,
    tenant: uuid.UUID,
    om: uuid.UUID,
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    w = Worker(baza, dir_proba, **MODUL).porneste()
    workeri.append(w)
    w.asteapta_pornit()
    bariera = threading.Barrier(2)
    cereri: list[efecte.Cerere] = []

    def cerere() -> None:
        bariera.wait(timeout=10)
        cereri.append(cere(tenant, lid))

    fire = [threading.Thread(target=cerere) for _ in range(2)]
    [f.start() for f in fire]
    [f.join(timeout=30) for f in fire]
    assert len(cereri) == 2 and cereri[0].efect.id == cereri[1].efect.id
    assert sorted(c.nou for c in cereri) == [False, True]
    e = cereri[0].efect
    asteapta(lambda: stare_efect(tenant, e.id) == "trimis", timeout_sec=60, mesaj="efectul trimis")
    assert len(platforma.postari()) == 1 and platforma.apeluri("trimite") == [f"trimite {e.cheia} ok"]
    with sesiune_tenant(tenant) as db:
        assert len(efecte.ale_livrabilului(db, lid)) == 1
    assert w.opreste_curat() == 0
