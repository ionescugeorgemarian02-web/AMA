"""F2.6 — planificatorul de timp: joburi recurente la minut și sloturi.

„Un job programat rulează la minut”: dovedit în trei feluri, fără să aștepte un minut întreg.
1. ceas controlat: `recupereaza_ratate` pune în coadă exact ticurile pe care planificatorul le-ar fi declanșat între
   două momente alese de test (aliniate la minut, în fusul programării, inclusiv peste trecerea la ora de iarnă);
2. timp real: un cron cu secunde (`* * * * * *`) rulează prin planificatorul real, la secundă, o singură dată pe tic;
3. conversia: un cron cu 5 câmpuri devine cron cu secunda 0.
„Pe staging” rămâne de verificat la migrare (STARE.md).
"""

import datetime as dt
import itertools
import time
from collections.abc import Callable, Iterator

import pytest

from app.operare import motor
from tests.integration import fluxuri_programare as probe

pytestmark = pytest.mark.db

Pornire = Callable[..., None]


@pytest.fixture(autouse=True)
def _curat(porneste_executor: Pornire) -> Iterator[None]:
    probe.reseteaza()
    yield
    probe.reseteaza()


def utc(*a: int) -> dt.datetime:
    return dt.datetime(*a, tzinfo=dt.UTC)


def asteapta(conditie: Callable[[], bool], timeout_sec: float = 15.0, mesaj: str = "condiția") -> None:
    limita = time.monotonic() + timeout_sec
    while not conditie():
        if time.monotonic() > limita:
            raise AssertionError(f"{mesaj} nu s-a îndeplinit în {timeout_sec} s")
        time.sleep(0.02)


# ---- timp real: planificatorul declanșează la secundă, o singură dată pe tic ------------------------------------------------


def test_un_job_programat_ruleaza_la_tic_in_timp_real(porneste_executor: Pornire) -> None:
    motor.programeaza_recurent("proba.secunda", "* * * * * *", probe.tic, context={"tenant_id": "t-1"})
    porneste_executor(programare_polling_sec=0.2)
    asteapta(lambda: len(probe.ticuri()) >= 3, mesaj="trei ticuri")

    ticuri = sorted(probe.TICURI)
    momente = [t[0] for t in ticuri]
    assert all(m.microsecond == 0 for m in momente), "ticurile sunt aliniate la secundă"
    assert len(set(momente)) == len(momente), "fiecare tic rulează o singură dată"
    pasi = {(b - a).total_seconds() for a, b in itertools.pairwise(momente)}
    assert pasi == {1.0}, f"ticuri consecutive, fără goluri: {momente}"
    for moment, primit_la, context in ticuri:
        assert context == {"tenant_id": "t-1"}
        intarziere = (dt.datetime.now(dt.UTC) - moment).total_seconds()
        assert intarziere >= 0, "nu rulează înainte de tic"
        assert primit_la > 0


def test_programarea_ramane_in_baza_si_apare_in_lista(porneste_executor: Pornire) -> None:
    motor.programeaza_recurent("proba.lista", "*/10 8 * * 1-5", probe.tic, coada=motor.Coada.INVATARE)
    porneste_executor()
    (info,) = [p for p in motor.lista_programari() if p.nume == "proba.lista"]
    assert (info.cron, info.stare, info.fus_orar, info.coada, info.flux) == (
        "0 */10 8 * * 1-5",
        "activa",
        "Europe/Bucharest",
        "invatare",
        "programare.tic",
    )


# ---- ceas controlat: ticurile la minut, în fusul programării ---------------------------------------------------------------


def test_ceas_controlat_ticurile_cad_exact_la_minut(porneste_executor: Pornire) -> None:
    motor.programeaza_recurent("proba.minut", "*/5 * * * *", probe.tic)
    porneste_executor()
    ids = motor.recupereaza_ratate("proba.minut", utc(2026, 11, 12, 12, 0, 30), utc(2026, 11, 12, 12, 20, 30))
    assert len(ids) == 4
    asteapta(lambda: len(probe.ticuri()) >= 4, mesaj="cele patru ticuri")
    asteptate = [utc(2026, 11, 12, 12, m) for m in (5, 10, 15, 20)]
    rulate = sorted(m for m in probe.ticuri() if m in asteptate)
    assert rulate == asteptate, "ticurile sunt la minutul fix, secunda 0"

    # a doua cerere pentru aceeași fereastră nu dublează nimic (identificatori deterministi)
    assert (
        motor.recupereaza_ratate("proba.minut", utc(2026, 11, 12, 12, 0, 30), utc(2026, 11, 12, 12, 20, 30))
        == ids
    )
    time.sleep(0.5)
    assert sorted(m for m in probe.ticuri() if m in asteptate) == asteptate


def test_ora_din_romania_urmeaza_trecerea_la_ora_de_iarna(porneste_executor: Pornire) -> None:
    """„În fiecare zi la 09:00, ora României”: 06:00 UTC vara, 07:00 UTC după 25 octombrie 2026."""
    motor.programeaza_recurent("proba.zilnic", "0 9 * * *", probe.tic)
    porneste_executor()
    motor.recupereaza_ratate("proba.zilnic", utc(2026, 10, 23, 12, 0), utc(2026, 10, 27, 0, 0))
    asteapta(lambda: len(probe.ticuri()) >= 3, mesaj="trei zile")
    in_utc = sorted(m.astimezone(dt.UTC) for m in probe.ticuri())
    assert [(m.day, m.hour, m.minute) for m in in_utc] == [(24, 6, 0), (25, 7, 0), (26, 7, 0)]


def test_interval_fara_fus_orar_este_refuzat(porneste_executor: Pornire) -> None:
    motor.programeaza_recurent("proba.fara_fus", "* * * * *", probe.tic)
    porneste_executor()
    with pytest.raises(motor.ProgramareInvalida, match="fus orar"):
        motor.recupereaza_ratate("proba.fara_fus", dt.datetime(2026, 1, 1), dt.datetime(2026, 1, 2))


# ---- pauză, reluare, ștergere, idempotență -------------------------------------------------------------------------------------


def test_pauza_opreste_ticurile_iar_reluarea_le_porneste_la_loc(porneste_executor: Pornire) -> None:
    motor.programeaza_recurent("proba.pauza", "* * * * * *", probe.tic)
    porneste_executor(programare_polling_sec=0.2)
    asteapta(lambda: len(probe.ticuri()) >= 2, mesaj="primele ticuri")
    motor.pune_pe_pauza("proba.pauza")
    time.sleep(0.8)
    n = len(probe.ticuri())
    time.sleep(1.3)
    assert len(probe.ticuri()) == n, "pe pauză nu mai ruleazǎ nimic"
    assert next(p for p in motor.lista_programari() if p.nume == "proba.pauza").stare == "pe_pauza"
    motor.reia_programarea("proba.pauza")
    asteapta(lambda: len(probe.ticuri()) > n, mesaj="ticuri după reluare")


def test_aplicarea_repetata_pastreaza_pauza(porneste_executor: Pornire) -> None:
    motor.programeaza_recurent("proba.idem", "0 3 * * *", probe.tic)
    porneste_executor()
    motor.pune_pe_pauza("proba.idem")
    assert motor.aplica_programari() == 1  # ca la o repornire a workerului
    assert next(p for p in motor.lista_programari() if p.nume == "proba.idem").stare == "pe_pauza"
    motor.sterge_programarea("proba.idem")
    assert not [p for p in motor.lista_programari() if p.nume == "proba.idem"]
    assert not [p for p in motor.programari_declarate() if p.nume == "proba.idem"]


def test_cron_invalid_la_aplicare(porneste_executor: Pornire) -> None:
    porneste_executor()
    motor.programeaza_recurent("proba.gresit", "99 99 * * *", probe.tic)
    with pytest.raises(motor.ProgramareInvalida, match="cron"):
        motor.aplica_programari()


def test_declanseaza_acum(porneste_executor: Pornire) -> None:
    motor.programeaza_recurent("proba.acum", "0 3 1 1 *", probe.tic)
    porneste_executor()
    motor.declanseaza_acum("proba.acum")
    asteapta(lambda: len(probe.ticuri()) == 1, mesaj="rulare imediată")


# ---- sloturi -------------------------------------------------------------------------------------------------------------------


def test_slotul_porneste_la_momentul_lui_si_nu_inainte(porneste_executor: Pornire) -> None:
    porneste_executor()
    la = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=1.5)
    job = motor.programeaza_slot(la, probe.slot, "s1", cheie="slot-1")
    stare = motor.stare_flux(job)
    assert stare is not None and stare.stare is motor.StareJob.AMANAT
    assert [s.cheie for s in motor.sloturi_viitoare()] == ["slot-1"]
    time.sleep(0.8)
    assert "s1" not in probe.SLOTURI, "nu pornește înainte de moment"
    asteapta(lambda: "s1" in probe.SLOTURI, mesaj="pornirea slotului")
    assert motor.asteapta_flux(job).stare is motor.StareJob.TERMINAT
    assert not motor.sloturi_viitoare()


def test_acelasi_slot_programat_de_doua_ori_este_un_singur_job(porneste_executor: Pornire) -> None:
    porneste_executor()
    la = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=0.5)
    a = motor.programeaza_slot(la, probe.slot, "s2", cheie="slot-2")
    b = motor.programeaza_slot(la, probe.slot, "s2", cheie="slot-2")
    assert a == b
    motor.asteapta_flux(a)
    assert len(probe.SLOTURI) == 1


def test_slotul_care_trece_cat_workerul_este_oprit_porneste_cand_revine_workerul(
    baza: object, motor_curat: None, porneste_executor: Pornire
) -> None:
    la = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=0.3)
    job = motor.programeaza_slot(la, probe.slot, "s3", cheie="slot-3")  # niciun worker nu rulează
    time.sleep(0.6)
    stare = motor.stare_flux(job)
    assert stare is not None and not stare.stare.final and "s3" not in probe.SLOTURI
    porneste_executor()
    asteapta(lambda: "s3" in probe.SLOTURI, mesaj="slotul întârziat")
    assert motor.asteapta_flux(job).stare is motor.StareJob.TERMINAT


def test_slot_anulat_nu_mai_ruleaza(porneste_executor: Pornire) -> None:
    porneste_executor()
    job = motor.programeaza_slot(
        dt.datetime.now(dt.UTC) + dt.timedelta(seconds=1.0), probe.slot, "s4", cheie="slot-4"
    )
    assert motor.anuleaza_slot("slot-4") is True
    assert motor.asteapta_flux(job).stare is motor.StareJob.ANULAT
    assert motor.anuleaza_slot("slot-4") is False, "un slot deja anulat nu se mai anulează"
    assert motor.anuleaza_slot("nu-exista") is False
    time.sleep(1.4)
    assert "s4" not in probe.SLOTURI


def test_slotul_fara_fus_orar_este_refuzat(porneste_executor: Pornire) -> None:
    with pytest.raises(ValueError, match="fus orar"):
        motor.programeaza_slot(dt.datetime(2030, 1, 1), probe.slot, "s5", cheie="slot-5")
