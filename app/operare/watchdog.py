"""Watchdog-ul workerului (22.3): semne de viață, joburi blocate, coada de erori, notificări.

Rulează ca fir în procesul `worker` (vezi `app/worker.py`). Ce face, în ordinea tabelului 22.3:

- **Worker fără semn de viață.** Fiecare worker bate la `AMA_WATCHDOG_BATAIE_SEC` (15 s) în
  `worker_semnale`. La pornire se citește rândul vechi: dacă instanța dinainte nu s-a oprit curat, a
  căzut (`repornit_dupa_cadere`); la a `AMA_WATCHDOG_PRAG_REPORNIRI`-a cădere într-o oră se anunță (o
  dată pe fereastră). Repornirea o face Docker (`restart: unless-stopped`); joburile se reiau la
  pornirea workerului. Dacă workerul nu mai reușește să bată (baza nu răspunde) mai mult de
  `AMA_WORKER_TIMEOUT_SEC`, iese singur ca Docker să-l repornească. Un alt worker care vede un rând
  fără bătaie îl semnalează (o dată).
- **Job peste timpul maxim.** Un job în lucru fără niciun pas încheiat mai mult decât timpul maxim al
  fluxului este oprit și reîncercat o dată; dacă se blochează din nou, intră în coada de erori.
- **Job care a eșuat.** Ce a aruncat o eroare după reîncercările pașilor, sau a căzut cu workerul de
  prea multe ori, intră în coada de erori cu contextul complet, grupat pe cauză (`coada_erori`).
- **Reluări.** O intrare reluată se închide singură când jobul reluat se termină cu bine.

Notificările trec prin `notificari.notifica` (nu aruncă). Textele conțin doar nume de fluxuri, pași,
cauze și numere: niciun conținut și nicio dată personală.
"""

import datetime as dt
import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import select

from app.config import get_settings
from app.db import sesiune_agentie
from app.logging import get_logger
from app.operare import coada_erori, motor, notificari, semnale
from app.operare.coada_erori import Severitate, Stare
from app.operare.notificari import Nivel
from app.operare.tabele import IntrareEroare

log = get_logger("app.watchdog")
COD_IESIRE_FARA_BAZA = 70


@dataclass
class Scanare:
    """Rezultatul unei treceri, pentru jurnal și teste."""

    ingerate: int = 0
    reluate_automat: int = 0
    blocate_escaladate: int = 0
    workeri_fara_semn: list[str] = field(default_factory=list)
    inchise_automat: int = 0
    erori: list[str] = field(default_factory=list)


def _iesire_fortata(cod: int) -> None:
    log.critical("watchdog: ies ca Docker să mă repornească", extra={"cod": cod})
    logging.shutdown()
    sys.stdout.flush()
    os._exit(cod)


def _notifica(nivel: Nivel, titlu: str, text: str, url: str = "/alerte") -> None:
    notificari.notifica(nivel, titlu, text, url=url)


class Watchdog:
    def __init__(
        self,
        worker_id: str,
        *,
        bataie_sec: float,
        scanare_sec: float,
        timeout_sec: float,
        prag_reporniri: int,
        fereastra_min: int,
        prag_crestere: int,
        versiune: str = "",
        iesire: Callable[[int], None] = _iesire_fortata,
        ceas: Callable[[], float] = time.monotonic,
    ) -> None:
        self.worker_id = worker_id
        self.bataie_sec, self.scanare_sec, self.timeout_sec = bataie_sec, scanare_sec, timeout_sec
        self.prag_reporniri, self.fereastra_min, self.prag_crestere = (
            prag_reporniri,
            fereastra_min,
            prag_crestere,
        )
        self.versiune = versiune
        self._iesire, self._ceas = iesire, ceas
        self._stop = threading.Event()
        self._fir: threading.Thread | None = None
        self._de_la_prima_esuare: float | None = None

    @classmethod
    def din_configurare(cls) -> "Watchdog":
        s = get_settings()
        return cls(
            s.worker_id,
            bataie_sec=s.watchdog_bataie_sec,
            scanare_sec=s.watchdog_scanare_sec,
            timeout_sec=s.worker_timeout_sec,
            prag_reporniri=s.watchdog_prag_reporniri,
            fereastra_min=s.watchdog_fereastra_min,
            prag_crestere=s.erori_prag_crestere,
            versiune=s.motor_versiune,
        )

    # --- ciclu de viață ---------------------------------------------------------------------------------
    def porneste(self) -> semnale.Pornire:
        """Înregistrează pornirea (și căderea dinainte, dacă a fost) și pornește firul."""
        with sesiune_agentie() as db:
            pornire = semnale.inregistreaza_pornire(
                db,
                self.worker_id,
                versiune=self.versiune,
                fereastra_min=self.fereastra_min,
                prag=self.prag_reporniri,
            )
        if pornire.dupa_cadere:
            log.warning(
                "workerul a fost repornit după o cădere",
                extra={"worker": self.worker_id, "reporniri_in_fereastra": pornire.reporniri_in_fereastra},
            )
        if pornire.alerta:
            _notifica(
                Nivel.IMPORTANT,
                f"Workerul a căzut de {pornire.reporniri_in_fereastra} ori în {self.fereastra_min} min",
                f"Worker {self.worker_id}. Joburile lui se reiau de la ultimul pas. Dacă se repetă, un job "
                "poate strica workerul: verifică ecranul Alerte.",
            )
        self._stop.clear()
        self._fir = threading.Thread(target=self._bucla, name="watchdog", daemon=True)
        self._fir.start()
        return pornire

    def opreste(self) -> None:
        """Oprește firul și marchează oprirea curată (altfel următoarea pornire ar număra o cădere)."""
        self._stop.set()
        if self._fir is not None:
            self._fir.join(timeout=max(5.0, self.bataie_sec * 2))
        try:
            with sesiune_agentie() as db:
                semnale.marcheaza_oprit_curat(db, self.worker_id)
        except Exception as exc:
            log.warning("nu am putut marca oprirea curată", extra={"tip_eroare": type(exc).__name__})

    # --- bucla ----------------------------------------------------------------------------------------------
    def bate(self) -> None:
        with sesiune_agentie() as db:
            semnale.bate_inima(db, self.worker_id)

    def _bucla(self) -> None:
        ultima_scanare = self._ceas()
        while not self._stop.wait(self.bataie_sec):
            self._bataie_cu_autoverificare()
            if self._ceas() - ultima_scanare >= self.scanare_sec:
                ultima_scanare = self._ceas()
                try:
                    self.scaneaza()
                except Exception as exc:  # o scanare stricată nu oprește bătăile
                    log.warning("scanarea watchdog a eșuat", extra={"tip_eroare": type(exc).__name__})

    def _bataie_cu_autoverificare(self) -> None:
        """Dacă baza nu răspunde mai mult de `timeout_sec`, workerul nu poate dovedi că trăiește: iese,
        iar Docker îl repornește (joburile lui se reiau)."""
        try:
            self.bate()
            self._de_la_prima_esuare = None
        except Exception as exc:
            acum = self._ceas()
            if self._de_la_prima_esuare is None:
                self._de_la_prima_esuare = acum
            log.warning("bătaia de inimă a eșuat", extra={"tip_eroare": type(exc).__name__})
            if acum - self._de_la_prima_esuare > self.timeout_sec:
                self._iesire(COD_IESIRE_FARA_BAZA)

    # --- scanarea -----------------------------------------------------------------------------------------
    def scaneaza(self) -> Scanare:
        rez = Scanare()
        for pas in (
            self._joburi_blocate,
            self._ingereaza_esecuri,
            self._workeri_fara_semn,
            self._sincronizeaza_reluari,
        ):
            try:
                pas(rez)
            except Exception as exc:  # un pas stricat nu îl blochează pe următorul
                rez.erori.append(f"{pas.__name__}: {type(exc).__name__}")
                log.warning(
                    "pas de scanare eșuat", extra={"pas": pas.__name__, "tip_eroare": type(exc).__name__}
                )
        return rez

    def _joburi_blocate(self, rez: Scanare) -> None:
        acum = dt.datetime.now(dt.UTC)
        for job in motor.joburi_in_lucru():
            limita = motor.timp_maxim_flux(job.nume)
            pasi = motor.pasi_job(job.id)
            progres = motor.ultimul_progres(job, pasi)
            if progres is None or (acum - progres).total_seconds() < limita:
                continue
            with sesiune_agentie() as db:
                existenta = db.execute(
                    select(IntrareEroare).where(IntrareEroare.workflow_id == job.id)
                ).scalar_one_or_none()
            if existenta is None or existenta.reluari == 0:
                self._opreste_si_reia(job, pasi, limita, rez)
            elif existenta.stare == Stare.RELUATA.value:
                self._escaladeaza_blocaj(job, pasi, limita, rez)

    def _opreste_si_reia(
        self, job: motor.DetaliiJob, pasi: list[motor.PasJob], limita: float, rez: Scanare
    ) -> None:
        motor.opreste_si_reia(job.id)
        mesaj = f"niciun pas încheiat în {int(limita)} s; oprit și reîncercat o dată"
        with sesiune_agentie() as db:
            coada_erori.inregistreaza(
                db,
                job,
                pasi,
                prag_crestere=self.prag_crestere,
                eroare_tip=coada_erori.PAS_TIMP_DEPASIT,
                eroare_mesaj=mesaj,
                stare=Stare.RELUATA,
                severitate=Severitate.INFORMATIV,
                reluari=1,
            )
        rez.reluate_automat += 1
        log.warning("job blocat, oprit și reîncercat", extra={"job": job.id, "flux": job.nume})

    def _escaladeaza_blocaj(
        self, job: motor.DetaliiJob, pasi: list[motor.PasJob], limita: float, rez: Scanare
    ) -> None:
        motor.anuleaza_job(job.id)
        mesaj = f"niciun pas încheiat în {int(limita)} s, nici după reîncercare; oprit"
        with sesiune_agentie() as db:
            r = coada_erori.inregistreaza(
                db,
                job,
                pasi,
                prag_crestere=self.prag_crestere,
                eroare_tip=coada_erori.PAS_TIMP_DEPASIT,
                eroare_mesaj=mesaj,
                stare=Stare.NOUA,
                severitate=Severitate.MAJOR,
                reluari=1,
            )
        rez.blocate_escaladate += 1
        if r is not None:
            _notifica(
                Nivel.IMPORTANT,
                f"Job blocat: {job.nume}",
                f"Nu a avansat în {int(limita)} s, nici după reîncercare. Jobul a fost oprit.",
                url=f"/alerte/{r.intrare.id}",
            )

    def _ingereaza_esecuri(self, rez: Scanare) -> None:
        esuate = motor.joburi_esuate()
        if not esuate:
            return
        with sesiune_agentie() as db:
            cunoscute = {
                r.workflow_id: (r.stare, r.reluat_ca)
                for r in db.execute(
                    select(IntrareEroare.workflow_id, IntrareEroare.stare, IntrareEroare.reluat_ca).where(
                        IntrareEroare.workflow_id.in_([j.id for j in esuate])
                    )
                )
            }
        for job in esuate:
            stare_cunoscuta, reluat_ca = cunoscute.get(job.id, (None, None))
            if stare_cunoscuta == Stare.INCHISA.value or stare_cunoscuta == Stare.NOUA.value:
                continue  # deja în coadă (sau o decizie înregistrată)
            if stare_cunoscuta == Stare.RELUATA.value and reluat_ca is not None:
                continue  # reluat prin bifurcare: jobul nou are propria lui intrare, originalul rămâne eșuat
            pasi = motor.pasi_job(job.id)
            with sesiune_agentie() as db:
                r = coada_erori.inregistreaza(db, job, pasi, prag_crestere=self.prag_crestere)
            if r is None:
                continue
            rez.ingerate += 1
            self._anunta(r)

    def _anunta(self, r: coada_erori.Rezultat) -> None:
        i = r.intrare
        url = f"/alerte/{i.id}"
        if r.prag_atins:
            _notifica(
                Nivel.IMPORTANT,
                "Erori care se tot repetă",
                f"{self.prag_crestere} joburi deschise cu aceeași cauză ({i.flux}, pasul {i.pas or '–'}).",
                url=url,
            )
        elif i.severitate in (Severitate.CRITIC.value, Severitate.MAJOR.value):
            _notifica(
                Nivel.CRITIC if i.severitate == Severitate.CRITIC.value else Nivel.IMPORTANT,
                f"Job eșuat: {i.flux}",
                f"Pasul {i.pas or '–'}; {i.eroare_tip}. Severitate {i.severitate}.",
                url=url,
            )
        elif r.cauza_noua:
            _notifica(
                Nivel.INFORMATIV,
                f"Cauză nouă de eroare: {i.flux}",
                f"Pasul {i.pas or '–'}; {i.eroare_tip}.",
                url,
            )

    def _workeri_fara_semn(self, rez: Scanare) -> None:
        with sesiune_agentie() as db:
            morti = semnale.fara_semn_de_viata(db, self.timeout_sec, exclus=self.worker_id)
            nume = [(w.worker_id, w.ultimul_semnal) for w in morti]
        for worker_id, ultimul in nume:
            rez.workeri_fara_semn.append(worker_id)
            _notifica(
                Nivel.IMPORTANT,
                "Worker fără semn de viață",
                f"Worker {worker_id} nu a dat semn din {ultimul:%H:%M:%S} UTC. Dacă nu repornește singur, "
                "verifică serviciul.",
            )

    def _sincronizeaza_reluari(self, rez: Scanare) -> None:
        with sesiune_agentie() as db:
            reluate = list(
                db.execute(select(IntrareEroare).where(IntrareEroare.stare == Stare.RELUATA.value)).scalars()
            )
            pentru_inchis: list[tuple[IntrareEroare, str]] = []
            for i in reluate:
                tinta = motor.detalii_job(i.reluat_ca or i.workflow_id)
                if tinta is None:
                    pentru_inchis.append((i, "jobul reluat nu mai există în baza motorului"))
                elif tinta.stare is motor.StareJob.TERMINAT:
                    pentru_inchis.append((i, "reluat și terminat cu succes"))
                elif i.reluat_ca and tinta.stare in (
                    motor.StareJob.ESUAT,
                    motor.StareJob.EPUIZAT,
                    motor.StareJob.ANULAT,
                ):
                    pentru_inchis.append((i, f"reluarea ({tinta.id}) a eșuat; vezi intrarea ei"))
            for i, motiv in pentru_inchis:
                coada_erori.inchide(db, i, motiv=motiv, utilizator_id=None)
                rez.inchise_automat += 1
        if rez.inchise_automat:
            log.info("intrări închise automat după reluare", extra={"numar": rez.inchise_automat})


__all__ = ["COD_IESIRE_FARA_BAZA", "Scanare", "Watchdog"]
